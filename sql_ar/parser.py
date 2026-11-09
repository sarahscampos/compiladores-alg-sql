# -*- coding: utf-8 -*-
"""Analisador sintático (SLY, LALR(1)) com ações semânticas que constroem a AST.

Cada método decorado com @_ é uma produção da gramática. O nome do método é
o não terminal do lado esquerdo e a string do decorador é o lado direito.
As produções recursivas estão marcadas com [RECURSIVA] nos comentários.

[MODIFICADO] Baseado no CalcParser do calc.py: a estrutura (classe Parser,
tokens vindos do lexer, @_ com ações, error) é a mesma, mas todas as
produções e ações semânticas são [NOVO]. As marcas indicam o que mudou.
"""
from sly import Parser

from .ast_sql import (Coluna, Comparacao, Consulta, E, Em, Existe, Join, Nao,
                      Numero, Ou, Subconsulta, Tabela, Texto)
from .erros import ErroSintatico, calcular_coluna
from .lexer import SqlLexer

# [NOVO] Nomes amigáveis dos tokens para as mensagens de erro
DESCRICAO_TOKENS = {
    'ID': 'identificador',
    'NUMBER': 'número',
    'STRING': 'texto entre aspas',
    'COMMA': "','",
    'DOT': "'.'",
    'STAR': "'*'",
    'SEMI': "';'",
    'LPAREN': "'('",
    'RPAREN': "')'",
    'EQ': "'='",
    'NE': "'!=' ou '<>'",
    'LT': "'<'",
    'GT': "'>'",
    'LE': "'<='",
    'GE': "'>='",
    '$end': 'fim da consulta',
}


def descrever_token(tipo):
    return DESCRICAO_TOKENS.get(tipo, tipo)


# [NOVO]
def tabela_producoes():
    """Tabela de tradução dirigida pela sintaxe: (número, produção, regra
    semântica). As produções vêm da gramática que o SLY montou e a regra vem
    da docstring de cada ação, então a tabela não fica diferente do código.
    A numeração é a do SLY (a mesma do arquivo de depuração parser.out).
    """
    linhas = []
    for producao in SqlParser._grammar.Productions[1:]:
        corpo = ' '.join(producao.prod) or 'ε'
        regra = (producao.func.__doc__ or '').strip()
        linhas.append((producao.number, f'{producao.name} → {corpo}', regra))
    return linhas


class SqlParser(Parser):
    # Recebe a lista de tokens vindos do Lexer
    tokens = SqlLexer.tokens

    # Símbolo inicial da gramática
    start = 'consulta'

    # [MODIFICADO] O calc.py usava a tabela `precedence` para desfazer a
    # ambiguidade de expr + expr * expr. Aqui não há tabela: a precedência de
    # OR/AND é codificada diretamente na gramática (condicao > conjuncao > fator).

    # [NOVO] Estado usado para mostrar derivação e árvores
    def __init__(self):
        self.texto = ''
        # Sequência de reduções feitas pelo parser LR, usada para mostrar
        # a derivação mais à direita e a árvore sintática.
        self.reducoes = []
        # Para cada redução, o valor (atributo .val) de cada não terminal do
        # lado direito: é o que a árvore de derivação anotada exibe.
        self.valores = []

    def analisar(self, texto):
        """Faz a análise léxica + sintática e devolve a AST (Consulta)."""
        self.texto = texto
        self.reducoes = []
        self.valores = []
        return self.parse(SqlLexer().tokenize(texto))

    def _registrar(self, p):
        """Anota a produção que acabou de ser reduzida.

        `self.production` é definido pelo SLY antes de chamar a ação; cada
        símbolo do lado direito é marcado como terminal ('T', lexema) ou
        não terminal ('N', nome).
        """
        producao = self.production
        lado_direito = []
        valores_filhos = []
        for i, simbolo in enumerate(producao.prod):
            # Atenção: durante parse() o SLY substitui self.tokens pelo
            # gerador de tokens; por isso o conjunto vem do lexer.
            if simbolo in SqlLexer.tokens:
                valor = p[i]
                lexema = str(Texto(valor)) if simbolo == 'STRING' else str(valor)
                lado_direito.append(('T', lexema))
            else:
                lado_direito.append(('N', simbolo))
                # Cópia: as ações de lista usam append, e sem ela todos os
                # níveis da árvore mostrariam a lista já completa.
                valor = p[i]
                valores_filhos.append(list(valor) if isinstance(valor, list) else valor)
        self.reducoes.append((producao.name, lado_direito))
        self.valores.append(valores_filhos)

    # [NOVO] Todas as produções abaixo substituem as regras expr do calc.py.
    # Cada docstring é a regra semântica da produção (--producoes).
    # ------------------------------------------------------------------
    # consulta → selecao fim
    # selecao  → SELECT lista_selecao FROM lista_tabelas clausula_where
    # ------------------------------------------------------------------

    @_('selecao fim')
    def consulta(self, p):
        """consulta.val = selecao.val"""
        self._registrar(p)
        return p.selecao

    # Separada de `consulta` para poder aparecer entre parênteses como
    # subconsulta, onde não pode haver ';'.
    @_('SELECT lista_selecao FROM lista_tabelas clausula_where')
    def selecao(self, p):
        """selecao.val = Consulta(lista_selecao.val, lista_tabelas.val, clausula_where.val)"""
        self._registrar(p)
        colunas = None if p.lista_selecao is None else tuple(p.lista_selecao)
        return Consulta(colunas, tuple(p.lista_tabelas), p.clausula_where)

    @_('SEMI')
    def fim(self, p):
        """fim: sem atributo (o ';' é opcional)"""
        self._registrar(p)

    @_('')
    def fim(self, p):
        """fim: sem atributo (o ';' é opcional)"""
        self._registrar(p)

    @_('WHERE condicao')
    def clausula_where(self, p):
        """clausula_where.val = condicao.val"""
        self._registrar(p)
        return p.condicao

    @_('')
    def clausula_where(self, p):
        """clausula_where.val = nulo"""
        self._registrar(p)
        return None

    # ------------------------------------------------------------------
    # Lista de seleção: '*' ou lista de colunas
    # ------------------------------------------------------------------

    @_('STAR')
    def lista_selecao(self, p):
        """lista_selecao.val = nulo (todas as colunas: não haverá π)"""
        self._registrar(p)
        return None

    @_('lista_colunas')
    def lista_selecao(self, p):
        """lista_selecao.val = lista_colunas.val"""
        self._registrar(p)
        return p.lista_colunas

    # [RECURSIVA à esquerda] caso recursivo: a lista já reconhecida é
    # estendida com mais uma coluna. Como a redução acontece da esquerda
    # para a direita, a ordem das colunas é preservada.
    @_('lista_colunas COMMA coluna')
    def lista_colunas(self, p):
        """lista_colunas.val = lista_colunas₁.val + [coluna.val]"""
        self._registrar(p)
        p.lista_colunas.append(p.coluna)
        return p.lista_colunas

    # Caso-base: uma única coluna inicia a lista
    @_('coluna')
    def lista_colunas(self, p):
        """lista_colunas.val = [coluna.val]"""
        self._registrar(p)
        return [p.coluna]

    @_('referencia')
    def coluna(self, p):
        """coluna.val = referencia.val"""
        self._registrar(p)
        return p.referencia

    # Identificador simples ou qualificado (tabela.coluna)
    @_('ID')
    def referencia(self, p):
        """referencia.val = Coluna(ID.lexema)"""
        self._registrar(p)
        return Coluna(p.ID, linha=p.lineno, indice=p.index)

    @_('ID DOT ID')
    def referencia(self, p):
        """referencia.val = Coluna(ID₂.lexema, tabela=ID₁.lexema)"""
        self._registrar(p)
        return Coluna(p.ID1, tabela=p.ID0, linha=p.lineno, indice=p.index)

    # ------------------------------------------------------------------
    # Cláusula FROM: tabelas separadas por vírgula e JOIN ... ON
    # ------------------------------------------------------------------

    # [RECURSIVA à esquerda] mesma estrutura de lista_colunas
    @_('lista_tabelas COMMA item_from')
    def lista_tabelas(self, p):
        """lista_tabelas.val = lista_tabelas₁.val + [item_from.val]"""
        self._registrar(p)
        p.lista_tabelas.append(p.item_from)
        return p.lista_tabelas

    @_('item_from')
    def lista_tabelas(self, p):
        """lista_tabelas.val = [item_from.val]"""
        self._registrar(p)
        return [p.item_from]

    # [RECURSIVA à esquerda] a JOIN b ON c1 JOIN d ON c2 = ((a ⋈ b) ⋈ d)
    @_('item_from JOIN tabela ON condicao',
       'item_from INNER JOIN tabela ON condicao')
    def item_from(self, p):
        """item_from.val = Join(item_from₁.val, tabela.val, condicao.val)"""
        self._registrar(p)
        return Join(p.item_from, p.tabela, p.condicao)

    @_('tabela')
    def item_from(self, p):
        """item_from.val = tabela.val"""
        self._registrar(p)
        return p.tabela

    @_('ID')
    def tabela(self, p):
        """tabela.val = Tabela(ID.lexema)"""
        self._registrar(p)
        return Tabela(p.ID, linha=p.lineno, indice=p.index)

    # Apelido (alias) de tabela: "alunos a" ou "alunos AS a"
    @_('ID ID', 'ID AS ID')
    def tabela(self, p):
        """tabela.val = Tabela(ID₁.lexema, apelido=ID₂.lexema)"""
        self._registrar(p)
        return Tabela(p.ID0, apelido=p.ID1, linha=p.lineno, indice=p.index)

    # ------------------------------------------------------------------
    # Condições: três níveis garantem OR < AND < NOT/parênteses
    # ------------------------------------------------------------------

    # [RECURSIVA à esquerda] OR, associativo à esquerda, menor precedência
    @_('condicao OR conjuncao')
    def condicao(self, p):
        """condicao.val = Ou(condicao₁.val, conjuncao.val)"""
        self._registrar(p)
        return Ou(p.condicao, p.conjuncao)

    @_('conjuncao')
    def condicao(self, p):
        """condicao.val = conjuncao.val"""
        self._registrar(p)
        return p.conjuncao

    # [RECURSIVA à esquerda] AND, associativo à esquerda, precede OR
    @_('conjuncao AND fator')
    def conjuncao(self, p):
        """conjuncao.val = E(conjuncao₁.val, fator.val)"""
        self._registrar(p)
        return E(p.conjuncao, p.fator)

    @_('fator')
    def conjuncao(self, p):
        """conjuncao.val = fator.val"""
        self._registrar(p)
        return p.fator

    # [RECURSIVA à direita] NOT NOT x
    @_('NOT fator')
    def fator(self, p):
        """fator.val = Nao(fator₁.val)"""
        self._registrar(p)
        return Nao(p.fator)

    # [AUTOINCORPORAÇÃO] condicao ⇒* ... ( condicao ) ...
    # Os parênteses apenas agrupam: a AST já guarda o agrupamento.
    @_('LPAREN condicao RPAREN')
    def fator(self, p):
        """fator.val = condicao.val (os parênteses só agrupam)"""
        self._registrar(p)
        return p.condicao

    # Aceito pela gramática para dar uma mensagem clara; a análise
    # semântica informa que EXISTS ainda não é traduzido.
    @_('EXISTS subconsulta')
    def fator(self, p):
        """fator.val = Existe(subconsulta.val) (rejeitado na análise semântica)"""
        self._registrar(p)
        return Existe(p.subconsulta)

    @_('comparacao')
    def fator(self, p):
        """fator.val = comparacao.val"""
        self._registrar(p)
        return p.comparacao

    @_('operando op_rel operando')
    def comparacao(self, p):
        """comparacao.val = Comparacao(operando₁.val, op_rel.val, operando₂.val)"""
        self._registrar(p)
        return Comparacao(p.operando0, p.op_rel, p.operando1)

    @_('operando IN subconsulta')
    def comparacao(self, p):
        """comparacao.val = Em(operando.val, subconsulta.val)"""
        self._registrar(p)
        return Em(p.operando, p.subconsulta)

    @_('operando NOT IN subconsulta')
    def comparacao(self, p):
        """comparacao.val = Em(operando.val, subconsulta.val, negado) (rejeitado na análise semântica)"""
        self._registrar(p)
        return Em(p.operando, p.subconsulta, negado=True)

    @_('EQ', 'NE', 'LT', 'GT', 'LE', 'GE')
    def op_rel(self, p):
        """op_rel.val = lexema do operador"""
        self._registrar(p)
        return p[0]

    @_('referencia')
    def operando(self, p):
        """operando.val = referencia.val"""
        self._registrar(p)
        return p.referencia

    @_('NUMBER')
    def operando(self, p):
        """operando.val = Numero(NUMBER.lexema)"""
        self._registrar(p)
        return Numero(p.NUMBER)

    @_('STRING')
    def operando(self, p):
        """operando.val = Texto(STRING.lexema)"""
        self._registrar(p)
        return Texto(p.STRING)

    @_('subconsulta')
    def operando(self, p):
        """operando.val = subconsulta.val"""
        self._registrar(p)
        return p.subconsulta

    # [AUTOINCORPORAÇÃO] consulta ⇒* ... ( selecao ) ...: uma consulta
    # inteira aparece dentro de outra, cercada por parênteses.
    @_('LPAREN selecao RPAREN')
    def subconsulta(self, p):
        """subconsulta.val = Subconsulta(selecao.val)"""
        self._registrar(p)
        return Subconsulta(p.selecao, linha=p.lineno, indice=p.index)

    # ------------------------------------------------------------------
    # [MODIFICADO] Tratamento de erros sintáticos. O calc.py imprimia o token;
    # aqui a análise para com linha, coluna e os tokens que eram esperados.
    # ------------------------------------------------------------------

    def _tokens_esperados(self):
        """Terminais que poderiam aparecer no lugar do token com erro.

        Na tabela LALR, estados com o mesmo núcleo são fundidos e suas
        ações de redução ficam com lookaheads de vários contextos. Para não
        listar tokens que na verdade não seriam aceitos, cada terminal é
        testado simulando as reduções sobre uma cópia da pilha de estados
        até ocorrer um deslocamento (aceito) ou uma falha (rejeitado).

        A tabela (_lrtable) e a pilha (statestack) são detalhes internos
        do SLY 0.5; se mudarem, a mensagem sai sem a lista de esperados.
        """
        try:
            acoes = self._lrtable.lr_action
            desvios = self._lrtable.lr_goto
            producoes = self._grammar.Productions
            pilha_original = list(self.statestack)
        except AttributeError:
            return []

        def aceita(terminal):
            pilha = list(pilha_original)
            while True:
                acao = acoes[pilha[-1]].get(terminal)
                if acao is None:
                    return False
                if acao >= 0:          # deslocamento (ou aceitação, se 0)
                    return True
                producao = producoes[-acao]
                if producao.len:
                    del pilha[-producao.len:]
                pilha.append(desvios[pilha[-1]][producao.name])

        candidatos = set(SqlLexer.tokens) | {'$end'}
        return sorted(descrever_token(t) for t in candidatos if aceita(t))

    def error(self, token):
        esperados = self._tokens_esperados()
        sufixo = f'; esperado: {", ".join(esperados)}' if esperados else ''
        if token is None:
            linhas = self.texto.split('\n')
            raise ErroSintatico(f'fim inesperado da consulta{sufixo}',
                                len(linhas), len(linhas[-1]) + 1)
        coluna = calcular_coluna(self.texto, token.index)
        raise ErroSintatico(
            f'token inesperado {token.value!r} ({descrever_token(token.type)}){sufixo}',
            token.lineno, coluna)
