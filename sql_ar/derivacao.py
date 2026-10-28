# -*- coding: utf-8 -*-
"""Reconstrução da derivação e da árvore sintática a partir das reduções LR.

Um parser LR (como o do SLY) executa uma derivação mais à direita "ao
contrário": cada redução desfaz um passo de derivação. Invertendo a lista
de reduções obtemos a derivação mais à direita a partir do símbolo inicial.
"""
from typing import NamedTuple


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


def arvore_sintatica(reducoes):
    """Monta a árvore sintática (concreta) usando uma pilha.

    As reduções chegam em pós-ordem: quando uma produção é reduzida, os
    nós dos seus não terminais já estão no topo da pilha.
    """
    pilha = []
    for esquerdo, direito in reducoes:
        qtd_nao_terminais = sum(1 for tipo, _ in direito if tipo == 'N')
        filhos_nt = pilha[len(pilha) - qtd_nao_terminais:]
        del pilha[len(pilha) - qtd_nao_terminais:]
        filhos = []
        for tipo, valor in direito:
            filhos.append(filhos_nt.pop(0) if tipo == 'N' else No(valor, [], True))
        pilha.append(No(esquerdo, filhos, False))
    return pilha[-1] if pilha else None


def formatar_arvore_sintatica(no, prefixo='', ultimo=True, raiz=True):
    rotulo = f'"{no.rotulo}"' if no.terminal else no.rotulo
    if raiz:
        linhas, prefixo_filhos = [rotulo], ''
    else:
        linhas = [prefixo + ('└── ' if ultimo else '├── ') + rotulo]
        prefixo_filhos = prefixo + ('    ' if ultimo else '│   ')
    if not no.terminal and not no.filhos:
        linhas.append(prefixo_filhos + '└── ε')   # produção vazia
    for i, filho in enumerate(no.filhos):
        linhas.append(formatar_arvore_sintatica(filho, prefixo_filhos,
                                                i == len(no.filhos) - 1, False))
    return '\n'.join(linhas)


def _texto_forma(forma):
    return ' '.join(valor for _, valor in forma) or 'ε'


def _texto_producao(esquerdo, direito):
    corpo = ' '.join(valor for _, valor in direito) or 'ε'
    return f'{esquerdo} → {corpo}'
