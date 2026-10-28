# -*- coding: utf-8 -*-
"""Análise semântica: verifica nomes de tabelas e qualificadores de colunas.

Sem um catálogo (esquema do banco) não é possível saber quais colunas cada
tabela possui; por isso as verificações se limitam ao que a própria consulta
declara na cláusula FROM.
"""
from .ast_sql import Coluna, Comparacao, E, Join, Nao, Ou, Tabela
from .erros import ErroSemantico, calcular_coluna


def analisar(consulta, texto=''):
    escopo = {}  # nome visível (apelido ou nome) -> Tabela
    for item in consulta.origem:
        _declarar_item(item, escopo, texto)

    for coluna in consulta.colunas or ():
        _verificar_coluna(coluna, escopo, texto)
    if consulta.where is not None:
        _verificar_condicao(consulta.where, escopo, texto)


def _declarar_item(item, escopo, texto):
    """Declara as tabelas de um item do FROM e valida as condições ON.

    Em SQL, a condição ON só enxerga as tabelas já unidas até aquele ponto,
    então ela é verificada logo após declarar o lado direito do JOIN.
    """
    if isinstance(item, Tabela):
        _declarar_tabela(item, escopo, texto)
        return {item.nome_visivel: item}
    locais = _declarar_item(item.esquerda, escopo, texto)
    locais.update(_declarar_item(item.direita, escopo, texto))
    _verificar_condicao(item.condicao, locais, texto)
    return locais


def _declarar_tabela(tabela, escopo, texto):
    nome = tabela.nome_visivel
    if nome in escopo:
        raise ErroSemantico(
            f"a tabela '{nome}' aparece mais de uma vez no FROM; "
            f"use apelidos diferentes (ex.: {tabela.nome} t1, {tabela.nome} t2)",
            *_posicao(tabela, texto))
    escopo[nome] = tabela


def _verificar_condicao(condicao, escopo, texto):
    if isinstance(condicao, Comparacao):
        for operando in (condicao.esquerda, condicao.direita):
            if isinstance(operando, Coluna):
                _verificar_coluna(operando, escopo, texto)
    elif isinstance(condicao, (E, Ou)):
        _verificar_condicao(condicao.esquerda, escopo, texto)
        _verificar_condicao(condicao.direita, escopo, texto)
    elif isinstance(condicao, Nao):
        _verificar_condicao(condicao.operando, escopo, texto)


def _verificar_coluna(coluna, escopo, texto):
    if coluna.tabela is None or coluna.tabela in escopo:
        return
    renomeadas = [t for t in escopo.values() if t.apelido and t.nome == coluna.tabela]
    if renomeadas:
        apelido = renomeadas[0].apelido
        mensagem = (f"a tabela '{coluna.tabela}' foi renomeada para '{apelido}'; "
                    f"use '{apelido}.{coluna.nome}'")
    else:
        visiveis = ', '.join(sorted(escopo)) or 'nenhuma'
        mensagem = (f"'{coluna}' referencia a tabela '{coluna.tabela}', que não está "
                    f"disponível neste ponto da consulta (tabelas visíveis: {visiveis})")
    raise ErroSemantico(mensagem, *_posicao(coluna, texto))


def _posicao(no, texto):
    if no.indice is None or not texto:
        return (None, None)
    return (no.linha, calcular_coluna(texto, no.indice))
