# -*- coding: utf-8 -*-
"""Expressões da Álgebra Relacional: estrutura, tradução a partir da AST e formatação.

A tradução segue a forma canônica de uma consulta SELECT-FROM-WHERE:

    SELECT L FROM R1, ..., Rn WHERE C   ⟶   π_{L}(σ_{C}(R1 × ... × Rn))

Primeiro a AST SQL é convertida em uma árvore de operadores relacionais;
só depois essa árvore é transformada em texto, evitando concatenar strings
durante a análise sintática.
"""
from dataclasses import dataclass
from functools import reduce
from typing import Union

from .ast_sql import Comparacao, Consulta, E, Join, Nao, Ou, Tabela

# --- Nós da Álgebra Relacional ---------------------------------------------


@dataclass(frozen=True)
class Relacao:
    nome: str


@dataclass(frozen=True)
class Renomeacao:          # ρ
    novo_nome: str
    expressao: 'ExprRelacional'


@dataclass(frozen=True)
class Selecao:             # σ
    condicao: object
    expressao: 'ExprRelacional'


@dataclass(frozen=True)
class Projecao:            # π
    atributos: tuple
    expressao: 'ExprRelacional'


@dataclass(frozen=True)
class ProdutoCartesiano:   # ×
    esquerda: 'ExprRelacional'
    direita: 'ExprRelacional'


@dataclass(frozen=True)
class Juncao:              # ⋈ (junção theta)
    esquerda: 'ExprRelacional'
    direita: 'ExprRelacional'
    condicao: object


ExprRelacional = Union[Relacao, Renomeacao, Selecao, Projecao,
                       ProdutoCartesiano, Juncao]

BINARIOS = (ProdutoCartesiano, Juncao)


# --- Tradução AST SQL -> Álgebra Relacional ---------------------------------


def traduzir(consulta: Consulta) -> ExprRelacional:
    # FROM R1, R2, ..., Rn  ->  ((R1 × R2) × ...) × Rn
    expressao = reduce(ProdutoCartesiano, map(_traduzir_item, consulta.origem))
    # WHERE C  ->  σ_C(...)
    if consulta.where is not None:
        expressao = Selecao(consulta.where, expressao)
    # SELECT L  ->  π_L(...); SELECT * não gera projeção
    if consulta.colunas is not None:
        expressao = Projecao(consulta.colunas, expressao)
    return expressao


def _traduzir_item(item):
    if isinstance(item, Tabela):
        relacao = Relacao(item.nome)
        # Apelido -> renomeação ρ_{apelido}(tabela)
        if item.apelido and item.apelido != item.nome:
            return Renomeacao(item.apelido, relacao)
        return relacao
    if isinstance(item, Join):
        return Juncao(_traduzir_item(item.esquerda),
                      _traduzir_item(item.direita),
                      item.condicao)
    raise TypeError(f'item de FROM desconhecido: {item!r}')


# --- Formatação das condições -----------------------------------------------

SIMBOLO_LOGICO = {Ou: '∨', E: '∧'}
# Quanto maior, mais forte a ligação
PRECEDENCIA = {Ou: 1, E: 2, Nao: 3, Comparacao: 4}


def formatar_condicao(condicao):
    if isinstance(condicao, Comparacao):
        return f'{condicao.esquerda} {condicao.operador} {condicao.direita}'
    if isinstance(condicao, Nao):
        return '¬' + _talvez_parenteses(condicao.operando, PRECEDENCIA[Nao])
    if isinstance(condicao, (E, Ou)):
        nivel = PRECEDENCIA[type(condicao)]
        esquerda = _talvez_parenteses(condicao.esquerda, nivel)
        # À direita, um operador de mesmo nível só aparece se o usuário
        # escreveu parênteses (a gramática é associativa à esquerda);
        # mantê-los preserva a estrutura original.
        direita = _talvez_parenteses(condicao.direita, nivel + 1)
        return f'{esquerda} {SIMBOLO_LOGICO[type(condicao)]} {direita}'
    raise TypeError(f'condição desconhecida: {condicao!r}')


def _talvez_parenteses(condicao, nivel_minimo):
    texto = formatar_condicao(condicao)
    if PRECEDENCIA[type(condicao)] < nivel_minimo:
        return f'({texto})'
    return texto


# --- Formatação das expressões relacionais ----------------------------------


def formatar(expressao) -> str:
    """Notação linear, ex.: π_{nome}(σ_{idade >= 18}(alunos))"""
    if isinstance(expressao, Relacao):
        return expressao.nome
    if isinstance(expressao, Renomeacao):
        return f'ρ_{{{expressao.novo_nome}}}({formatar(expressao.expressao)})'
    if isinstance(expressao, Selecao):
        return f'σ_{{{formatar_condicao(expressao.condicao)}}}({formatar(expressao.expressao)})'
    if isinstance(expressao, Projecao):
        atributos = ', '.join(map(str, expressao.atributos))
        return f'π_{{{atributos}}}({formatar(expressao.expressao)})'
    if isinstance(expressao, BINARIOS):
        esquerda = formatar(expressao.esquerda)
        direita = formatar(expressao.direita)
        # × é associativo: (R × S) × T pode ser escrito R × S × T.
        # Nos demais casos um operando binário fica entre parênteses.
        assoc = (isinstance(expressao, ProdutoCartesiano)
                 and isinstance(expressao.esquerda, ProdutoCartesiano))
        if isinstance(expressao.esquerda, BINARIOS) and not assoc:
            esquerda = f'({esquerda})'
        if isinstance(expressao.direita, BINARIOS):
            direita = f'({direita})'
        return f'{esquerda} {_rotulo_binario(expressao)} {direita}'
    raise TypeError(f'expressão desconhecida: {expressao!r}')


def _rotulo_binario(expressao):
    if isinstance(expressao, Juncao):
        return f'⋈_{{{formatar_condicao(expressao.condicao)}}}'
    return '×'


def formatar_arvore(expressao, prefixo='', ultimo=True, raiz=True) -> str:
    """Árvore de operadores (útil para visualizar a ordem de avaliação)."""
    if isinstance(expressao, Relacao):
        rotulo, filhos = expressao.nome, []
    elif isinstance(expressao, Renomeacao):
        rotulo, filhos = f'ρ {expressao.novo_nome}', [expressao.expressao]
    elif isinstance(expressao, Selecao):
        rotulo, filhos = f'σ {formatar_condicao(expressao.condicao)}', [expressao.expressao]
    elif isinstance(expressao, Projecao):
        rotulo = 'π ' + ', '.join(map(str, expressao.atributos))
        filhos = [expressao.expressao]
    elif isinstance(expressao, Juncao):
        rotulo = f'⋈ {formatar_condicao(expressao.condicao)}'
        filhos = [expressao.esquerda, expressao.direita]
    elif isinstance(expressao, ProdutoCartesiano):
        rotulo, filhos = '×', [expressao.esquerda, expressao.direita]
    else:
        raise TypeError(f'expressão desconhecida: {expressao!r}')

    if raiz:
        linhas = [rotulo]
        prefixo_filhos = ''
    else:
        linhas = [prefixo + ('└── ' if ultimo else '├── ') + rotulo]
        prefixo_filhos = prefixo + ('    ' if ultimo else '│   ')
    for i, filho in enumerate(filhos):
        linhas.append(formatar_arvore(filho, prefixo_filhos,
                                      i == len(filhos) - 1, raiz=False))
    return '\n'.join(linhas)
