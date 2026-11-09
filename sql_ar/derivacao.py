# -*- coding: utf-8 -*-
# [NOVO] Arquivo criado neste trabalho; não existe no exemplo calc.py.
"""Reconstrução da derivação e da árvore sintática a partir das reduções LR.

Um parser LR (como o do SLY) executa uma derivação mais à direita "ao
contrário": cada redução desfaz um passo de derivação. Invertendo a lista
de reduções obtemos a derivação mais à direita a partir do símbolo inicial.
"""
from typing import NamedTuple

from .ast_sql import (Comparacao, Consulta, E, Em, Existe, Join, Nao, Ou, Tabela,
                      TabelaDerivada)


def derivacao_mais_a_direita(reducoes, inicial='consulta'):
    """Devolve a lista de formas sentenciais, da primeira (símbolo inicial)
    até a última (a sentença formada só por terminais)."""
    forma = [('N', inicial)]
    passos = [(None, _texto_forma(forma))]
    for esquerdo, direito in reversed(reducoes):
        # Numa derivação mais à direita expande-se sempre o não terminal
        # mais à direita, que é exatamente o lado esquerdo desta redução.
        posicao = max(i for i, (tipo, _) in enumerate(forma) if tipo == 'N')
        assert forma[posicao][1] == esquerdo, 'reduções fora de ordem'
        forma = forma[:posicao] + direito + forma[posicao + 1:]
        passos.append((_texto_producao(esquerdo, direito), _texto_forma(forma)))
    return passos


def formatar_derivacao(reducoes, inicial='consulta'):
    linhas = []
    for producao, forma in derivacao_mais_a_direita(reducoes, inicial):
        if producao is None:
            linhas.append(f'    {forma}')
        else:
            linhas.append(f' ⇒  {forma}')
            linhas.append(f'        [{producao}]')
    return '\n'.join(linhas)


class No(NamedTuple):
    rotulo: str
    filhos: list
    terminal: bool
    # Atributo sintetizado (.val) do não terminal, para a árvore anotada
    valor: object = None


# Não terminais cuja ação não produz atributo (o ';' opcional)
SEM_ATRIBUTO = {'fim'}


def arvore_sintatica(reducoes, valores=None, valor_raiz=None):
    """Monta a árvore sintática (concreta) usando uma pilha.

    As reduções chegam em pós-ordem: quando uma produção é reduzida, os
    nós dos seus não terminais já estão no topo da pilha. `valores` traz,
    para cada redução, os atributos dos não terminais do lado direito.
    """
    pilha = []
    for i, (esquerdo, direito) in enumerate(reducoes):
        qtd_nao_terminais = sum(1 for tipo, _ in direito if tipo == 'N')
        filhos_nt = pilha[len(pilha) - qtd_nao_terminais:]
        del pilha[len(pilha) - qtd_nao_terminais:]
        if valores is not None:
            filhos_nt = [f._replace(valor=v) for f, v in zip(filhos_nt, valores[i])]
        filhos = []
        for tipo, valor in direito:
            filhos.append(filhos_nt.pop(0) if tipo == 'N' else No(valor, [], True))
        pilha.append(No(esquerdo, filhos, False))
    if not pilha:
        return None
    return pilha[-1]._replace(valor=valor_raiz)


def rotulo_anotado(no):
    """'lista_colunas.val = [nome, idade]' para não terminais."""
    if no.terminal or no.rotulo in SEM_ATRIBUTO:
        return None
    return f'{no.rotulo}.val = {formatar_valor(no.valor)}'


def formatar_valor(valor):
    """Escreve um atributo (nó da AST, lista ou lexema) de forma compacta."""
    if valor is None:
        return 'nulo'
    if isinstance(valor, (list, tuple)):
        return '[' + ', '.join(formatar_valor(v) for v in valor) + ']'
    if isinstance(valor, Tabela):
        return f'{valor.nome} AS {valor.apelido}' if valor.apelido else valor.nome
    if isinstance(valor, TabelaDerivada):
        return f'(SELECT ...) AS {valor.apelido}' if valor.apelido else '(SELECT ...)'
    if isinstance(valor, Join):
        return (f'{formatar_valor(valor.esquerda)} JOIN {formatar_valor(valor.direita)} '
                f'ON {formatar_valor(valor.condicao)}')
    if isinstance(valor, Comparacao):
        return f'{valor.esquerda} {valor.operador} {valor.direita}'
    if isinstance(valor, (E, Ou)):
        operador = 'AND' if isinstance(valor, E) else 'OR'
        return (f'{_agrupar(valor.esquerda, valor, False)} {operador} '
                f'{_agrupar(valor.direita, valor, True)}')
    if isinstance(valor, Nao):
        return f'NOT {_agrupar(valor.operando, valor, True)}'
    if isinstance(valor, Em):
        return f'{valor.operando} {"NOT IN" if valor.negado else "IN"} {valor.subconsulta}'
    if isinstance(valor, Existe):
        return f'EXISTS {valor.subconsulta}'
    if isinstance(valor, Consulta):
        colunas = '*' if valor.colunas is None else formatar_valor(valor.colunas)
        return (f'Consulta(colunas={colunas}, origem={formatar_valor(valor.origem)}, '
                f'where={formatar_valor(valor.where)})')
    if isinstance(valor, str):
        return f'"{valor}"'   # lexema, como o operador relacional
    return str(valor)         # Coluna, Numero, Texto, Subconsulta


def _agrupar(filho, pai, a_direita):
    """Parênteses só onde mudam o sentido: OR dentro de AND, NOT de algo
    composto, e o mesmo operador à direita (que veio de parênteses)."""
    texto = formatar_valor(filho)
    composto = isinstance(filho, (E, Ou))
    if not composto:
        return texto
    mesmo_a_direita = a_direita and type(filho) is type(pai)
    if isinstance(pai, Nao) or (isinstance(pai, E) and isinstance(filho, Ou)) or mesmo_a_direita:
        return f'({texto})'
    return texto


def formatar_arvore_sintatica(no, prefixo='', ultimo=True, raiz=True, anotada=False):
    rotulo = f'"{no.rotulo}"' if no.terminal else no.rotulo
    if anotada and rotulo_anotado(no):
        rotulo = rotulo_anotado(no)
    if raiz:
        linhas, prefixo_filhos = [rotulo], ''
    else:
        linhas = [prefixo + ('└── ' if ultimo else '├── ') + rotulo]
        prefixo_filhos = prefixo + ('    ' if ultimo else '│   ')
    if not no.terminal and not no.filhos:
        linhas.append(prefixo_filhos + '└── ε')   # produção vazia
    for i, filho in enumerate(no.filhos):
        linhas.append(formatar_arvore_sintatica(filho, prefixo_filhos,
                                                i == len(no.filhos) - 1, False, anotada))
    return '\n'.join(linhas)


def _texto_forma(forma):
    return ' '.join(valor for _, valor in forma) or 'ε'


def _texto_producao(esquerdo, direito):
    corpo = ' '.join(valor for _, valor in direito) or 'ε'
    return f'{esquerdo} → {corpo}'
