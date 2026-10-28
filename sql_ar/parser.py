# -*- coding: utf-8 -*-
"""Analisador sintático (SLY, LALR(1)) com ações semânticas que constroem a AST.

Cada método decorado com @_ é uma produção da gramática. O nome do método é
o não terminal do lado esquerdo e a string do decorador é o lado direito.
As produções recursivas estão marcadas com [RECURSIVA] nos comentários.
"""
from sly import Parser

from .ast_sql import (Coluna, Comparacao, Consulta, E, Join, Nao, Numero, Ou,
                      Tabela, Texto)
from .erros import ErroSintatico, calcular_coluna
from .lexer import SqlLexer

# Nomes amigáveis dos tokens para as mensagens de erro
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


class SqlParser(Parser):
    # Recebe a lista de tokens vindos do Lexer
    tokens = SqlLexer.tokens

    # Símbolo inicial da gramática
    start = 'consulta'

    # Não há tabela de precedência: a precedência de OR/AND é codificada
    # diretamente na gramática (níveis condicao > conjuncao > fator).

    def __init__(self):
        self.texto = ''
        # Sequência de reduções feitas pelo parser LR, usada para mostrar
        # a derivação mais à direita e a árvore sintática.
        self.reducoes = []

    def analisar(self, texto):
        """Faz a análise léxica + sintática e devolve a AST (Consulta)."""
        self.texto = texto
        self.reducoes = []
        return self.parse(SqlLexer().tokenize(texto))

    def _registrar(self, p):
        """Anota a produção que acabou de ser reduzida.

        `self.production` é definido pelo SLY antes de chamar a ação; cada
        símbolo do lado direito é marcado como terminal ('T', lexema) ou
        não terminal ('N', nome).
        """
        producao = self.production
        lado_direito = []
        for i, simbolo in enumerate(producao.prod):
            # Atenção: durante parse() o SLY substitui self.tokens pelo
            # gerador de tokens; por isso o conjunto vem do lexer.
            if simbolo in SqlLexer.tokens:
                valor = p[i]
                lexema = str(Texto(valor)) if simbolo == 'STRING' else str(valor)
                lado_direito.append(('T', lexema))
            else:
                lado_direito.append(('N', simbolo))
        self.reducoes.append((producao.name, lado_direito))

    # ------------------------------------------------------------------
    # consulta → SELECT lista_selecao FROM lista_tabelas clausula_where fim
    # ------------------------------------------------------------------

    @_('SELECT lista_selecao FROM lista_tabelas clausula_where fim')
    def consulta(self, p):
        self._registrar(p)
        colunas = None if p.lista_selecao is None else tuple(p.lista_selecao)
        return Consulta(colunas, tuple(p.lista_tabelas), p.clausula_where)

    @_('SEMI')
    def fim(self, p):
        self._registrar(p)

    @_('')
    def fim(self, p):
        self._registrar(p)

    @_('WHERE condicao')
    def clausula_where(self, p):
        self._registrar(p)
        return p.condicao

    @_('')
    def clausula_where(self, p):
        self._registrar(p)
        return None

    # ------------------------------------------------------------------
    # Lista de seleção: '*' ou lista de colunas
    # ------------------------------------------------------------------

    @_('STAR')
    def lista_selecao(self, p):
        self._registrar(p)
        return None

    @_('lista_colunas')
    def lista_selecao(self, p):
        self._registrar(p)
        return p.lista_colunas

    # [RECURSIVA à esquerda] caso recursivo: a lista já reconhecida é
    # estendida com mais uma coluna. Como a redução acontece da esquerda
    # para a direita, a ordem das colunas é preservada.
    @_('lista_colunas COMMA coluna')
    def lista_colunas(self, p):
        self._registrar(p)
        p.lista_colunas.append(p.coluna)
        return p.lista_colunas

    # Caso-base: uma única coluna inicia a lista
    @_('coluna')
    def lista_colunas(self, p):
        self._registrar(p)
        return [p.coluna]

    @_('referencia')
    def coluna(self, p):
        self._registrar(p)
        return p.referencia

    # Identificador simples ou qualificado (tabela.coluna)
    @_('ID')
    def referencia(self, p):
        self._registrar(p)
        return Coluna(p.ID, linha=p.lineno, indice=p.index)

    @_('ID DOT ID')
    def referencia(self, p):
        self._registrar(p)
        return Coluna(p.ID1, tabela=p.ID0, linha=p.lineno, indice=p.index)

    # ------------------------------------------------------------------
    # Cláusula FROM: tabelas separadas por vírgula e JOIN ... ON
    # ------------------------------------------------------------------

    # [RECURSIVA à esquerda] mesma estrutura de lista_colunas
    @_('lista_tabelas COMMA item_from')
    def lista_tabelas(self, p):
        self._registrar(p)
        p.lista_tabelas.append(p.item_from)
        return p.lista_tabelas

    @_('item_from')
    def lista_tabelas(self, p):
        self._registrar(p)
        return [p.item_from]

    # [RECURSIVA à esquerda] a JOIN b ON c1 JOIN d ON c2 = ((a ⋈ b) ⋈ d)
    @_('item_from JOIN tabela ON condicao',
       'item_from INNER JOIN tabela ON condicao')
    def item_from(self, p):
        self._registrar(p)
        return Join(p.item_from, p.tabela, p.condicao)

    @_('tabela')
    def item_from(self, p):
        self._registrar(p)
        return p.tabela

    @_('ID')
    def tabela(self, p):
        self._registrar(p)
        return Tabela(p.ID, linha=p.lineno, indice=p.index)

    # Apelido (alias) de tabela: "alunos a" ou "alunos AS a"
    @_('ID ID', 'ID AS ID')
    def tabela(self, p):
        self._registrar(p)
        return Tabela(p.ID0, apelido=p.ID1, linha=p.lineno, indice=p.index)

    # ------------------------------------------------------------------
    # Condições: três níveis garantem OR < AND < NOT/parênteses
    # ------------------------------------------------------------------

    # [RECURSIVA à esquerda] OR, associativo à esquerda, menor precedência
    @_('condicao OR conjuncao')
    def condicao(self, p):
        self._registrar(p)
        return Ou(p.condicao, p.conjuncao)

    @_('conjuncao')
    def condicao(self, p):
        self._registrar(p)
        return p.conjuncao

    # [RECURSIVA à esquerda] AND, associativo à esquerda, precede OR
    @_('conjuncao AND fator')
    def conjuncao(self, p):
        self._registrar(p)
        return E(p.conjuncao, p.fator)

    @_('fator')
    def conjuncao(self, p):
        self._registrar(p)
        return p.fator

    # [RECURSIVA à direita] NOT NOT x
    @_('NOT fator')
    def fator(self, p):
        self._registrar(p)
        return Nao(p.fator)

    # [AUTOINCORPORAÇÃO] condicao ⇒* ... ( condicao ) ...
    # Os parênteses apenas agrupam: a AST já guarda o agrupamento.
    @_('LPAREN condicao RPAREN')
    def fator(self, p):
        self._registrar(p)
        return p.condicao

    @_('comparacao')
    def fator(self, p):
        self._registrar(p)
        return p.comparacao

    @_('operando op_rel operando')
    def comparacao(self, p):
        self._registrar(p)
        return Comparacao(p.operando0, p.op_rel, p.operando1)

    @_('EQ', 'NE', 'LT', 'GT', 'LE', 'GE')
    def op_rel(self, p):
        self._registrar(p)
        return p[0]

    @_('referencia')
    def operando(self, p):
        self._registrar(p)
        return p.referencia

    @_('NUMBER')
    def operando(self, p):
        self._registrar(p)
        return Numero(p.NUMBER)

    @_('STRING')
    def operando(self, p):
        self._registrar(p)
        return Texto(p.STRING)

    # ------------------------------------------------------------------
    # Tratamento de erros sintáticos
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
