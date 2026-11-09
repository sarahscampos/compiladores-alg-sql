# -*- coding: utf-8 -*-
# [NOVO] Arquivo criado neste trabalho; não existe no exemplo calc.py.
"""Expressões da Álgebra Relacional: estrutura, tradução a partir da AST e formatação.

A tradução segue a forma canônica de uma consulta SELECT-FROM-WHERE:

    SELECT L FROM R1, ..., Rn WHERE C   ⟶   π_{L}(σ_{C}(R1 × ... × Rn))

Uma subconsulta no FROM vira uma relação renomeada: FROM (SELECT ...) t
gera ρ_{t}(...). Uma condição do WHERE com subconsulta vira uma semijunção (⋉), que mantém
as linhas da esquerda para as quais existe alguma linha da direita que
satisfaz a condição:

    SELECT L FROM R WHERE C AND x > (SELECT y FROM S)
        ⟶   π_{L}(σ_{C}(R ⋉_{R.x > s1.y} ρ_{s1}(π_{y}(S))))

Primeiro a AST SQL é convertida em uma árvore de operadores relacionais;
só depois essa árvore é transformada em texto, evitando concatenar strings
durante a análise sintática.
"""
from dataclasses import dataclass
from functools import reduce
from itertools import count
from typing import Union

from .ast_sql import (Coluna, Comparacao, Consulta, E, Em, Join, Nao, Ou,
                      Subconsulta, Tabela, TabelaDerivada, separar_conjuncoes)

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


@dataclass(frozen=True)
class Semijuncao:          # ⋉ (semijunção theta): só as colunas da esquerda
    esquerda: 'ExprRelacional'
    direita: 'ExprRelacional'
    condicao: object


ExprRelacional = Union[Relacao, Renomeacao, Selecao, Projecao,
                       ProdutoCartesiano, Juncao, Semijuncao]

BINARIOS = (ProdutoCartesiano, Juncao, Semijuncao)
COM_CONDICAO = (Juncao, Semijuncao)


# --- Tradução AST SQL -> Álgebra Relacional ---------------------------------


def traduzir(consulta: Consulta) -> ExprRelacional:
    """Pressupõe uma consulta já validada pela análise semântica."""
    # Os apelidos das subconsultas (sub1, sub2, ...) não podem coincidir com
    # nenhum nome de tabela usado em qualquer nível da consulta.
    return _traduzir_consulta(consulta, _nomes_de_tabelas(consulta), count(1))


def _traduzir_consulta(consulta, usados, contador):
    # FROM R1, R2, ..., Rn  ->  ((R1 × R2) × ...) × Rn
    expressao = reduce(ProdutoCartesiano,
                       [_traduzir_item(item, usados, contador) for item in consulta.origem])
    if consulta.where is not None:
        conjuncoes = separar_conjuncoes(consulta.where)
        if any(_subconsulta_de(c) for c in conjuncoes):
            comuns = []
            for condicao in conjuncoes:
                if _subconsulta_de(condicao):
                    # x op (SELECT ...)  ->  ... ⋉_{x op sub.y} ρ_{sub}(...)
                    expressao = _semijuncao(expressao, condicao, consulta, usados, contador)
                else:
                    comuns.append(condicao)
            if comuns:
                expressao = Selecao(reduce(E, comuns), expressao)
        else:
            # WHERE C  ->  σ_C(...), mantendo a condição como foi escrita
            expressao = Selecao(consulta.where, expressao)
    # SELECT L  ->  π_L(...); SELECT * não gera projeção
    if consulta.colunas is not None:
        expressao = Projecao(consulta.colunas, expressao)
    return expressao


def _semijuncao(expressao, condicao, consulta, usados, contador):
    subconsulta = _subconsulta_de(condicao)
    apelido = _novo_apelido(usados, contador)
    interna = _traduzir_consulta(subconsulta.consulta, usados, contador)
    coluna = Coluna(subconsulta.consulta.colunas[0].nome, tabela=apelido)

    tabela_unica = _tabela_unica(consulta)
    if isinstance(condicao, Em):
        # x IN (SELECT y ...)  ->  condição x = sub.y
        teta = Comparacao(_qualificar(condicao.operando, tabela_unica), '=', coluna)
    else:
        lados = [coluna if o is subconsulta else _qualificar(o, tabela_unica)
                 for o in (condicao.esquerda, condicao.direita)]
        teta = Comparacao(lados[0], condicao.operador, lados[1])
    return Semijuncao(expressao, Renomeacao(apelido, interna), teta)


def _subconsulta_de(condicao):
    if isinstance(condicao, Em):
        return condicao.subconsulta
    if isinstance(condicao, Comparacao):
        for operando in (condicao.esquerda, condicao.direita):
            if isinstance(operando, Subconsulta):
                return operando
    return None


def _qualificar(operando, tabela):
    """Na condição da semijunção as colunas dos dois lados se encontram; com
    uma tabela só no FROM externo, a coluna sem tabela é dela."""
    if isinstance(operando, Coluna) and operando.tabela is None and tabela:
        return Coluna(operando.nome, tabela=tabela)
    return operando


def _tabela_unica(consulta):
    if len(consulta.origem) == 1 and isinstance(consulta.origem[0], (Tabela, TabelaDerivada)):
        return consulta.origem[0].nome_visivel
    return None


def _novo_apelido(usados, contador):
    while True:
        apelido = f'sub{next(contador)}'
        if apelido not in usados:
            usados.add(apelido)
            return apelido


def _nomes_de_tabelas(consulta):
    nomes = set()
    pendentes = [consulta]
    while pendentes:
        atual = pendentes.pop()
        itens = list(atual.origem)
        while itens:
            item = itens.pop()
            if isinstance(item, Join):
                itens += [item.esquerda, item.direita]
            elif isinstance(item, TabelaDerivada):
                nomes.add(item.apelido)
                pendentes.append(item.consulta)
            else:
                nomes |= {item.nome, item.nome_visivel}
        for condicao in separar_conjuncoes(atual.where) if atual.where else ():
            if _subconsulta_de(condicao):
                pendentes.append(_subconsulta_de(condicao).consulta)
    return nomes


def _traduzir_item(item, usados, contador):
    if isinstance(item, TabelaDerivada):
        # FROM (SELECT ...) t  ->  ρ_{t}(tradução da subconsulta)
        return Renomeacao(item.apelido, _traduzir_consulta(item.consulta, usados, contador))
    if isinstance(item, Tabela):
        relacao = Relacao(item.nome)
        # Apelido -> renomeação ρ_{apelido}(tabela)
        if item.apelido and item.apelido != item.nome:
            return Renomeacao(item.apelido, relacao)
        return relacao
    if isinstance(item, Join):
        return Juncao(_traduzir_item(item.esquerda, usados, contador),
                      _traduzir_item(item.direita, usados, contador),
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
    if isinstance(expressao, Semijuncao):
        return f'⋉_{{{formatar_condicao(expressao.condicao)}}}'
    return '×'


def decompor(expressao):
    """Separa um nó em (símbolo do operador, detalhe, filhos).

    É a visão de "árvore de consulta" usada pela árvore em texto e pelo grafo.
    Relações são as folhas: não têm símbolo, só o nome.
    """
    if isinstance(expressao, Relacao):
        return '', expressao.nome, []
    if isinstance(expressao, Renomeacao):
        return 'ρ', expressao.novo_nome, [expressao.expressao]
    if isinstance(expressao, Selecao):
        return 'σ', formatar_condicao(expressao.condicao), [expressao.expressao]
    if isinstance(expressao, Projecao):
        atributos = ', '.join(map(str, expressao.atributos))
        return 'π', atributos, [expressao.expressao]
    if isinstance(expressao, Juncao):
        return ('⋈', formatar_condicao(expressao.condicao),
                [expressao.esquerda, expressao.direita])
    if isinstance(expressao, Semijuncao):
        return ('⋉', formatar_condicao(expressao.condicao),
                [expressao.esquerda, expressao.direita])
    if isinstance(expressao, ProdutoCartesiano):
        return '×', '', [expressao.esquerda, expressao.direita]
    raise TypeError(f'expressão desconhecida: {expressao!r}')


def formatar_arvore(expressao, prefixo='', ultimo=True, raiz=True) -> str:
    """Árvore de operadores (útil para visualizar a ordem de avaliação)."""
    simbolo, detalhe, filhos = decompor(expressao)
    rotulo = ' '.join(parte for parte in (simbolo, detalhe) if parte)

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
