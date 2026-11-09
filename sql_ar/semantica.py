# -*- coding: utf-8 -*-
"""Análise semântica: verifica nomes de tabelas, qualificadores de colunas e
onde as subconsultas aparecem.

Sem um catálogo (esquema do banco) não é possível saber quais colunas cada
tabela possui; por isso as verificações se limitam ao que a própria consulta
declara na cláusula FROM.
"""
from .ast_sql import (Coluna, Comparacao, E, Em, Existe, Nao, Ou, Subconsulta,
                      Tabela, separar_conjuncoes)
from .erros import ErroSemantico, calcular_coluna


def analisar(consulta, texto='', externos=()):
    """`externos` são os escopos das consultas que envolvem esta (se ela
    for uma subconsulta); servem para reconhecer subconsultas correlacionadas."""
    escopo = {}  # nome visível (apelido ou nome) -> Tabela
    for item in consulta.origem:
        _declarar_item(item, escopo, texto, externos)

    for coluna in consulta.colunas or ():
        _verificar_coluna(coluna, escopo, texto, externos)
    if consulta.where is not None:
        for condicao in separar_conjuncoes(consulta.where):
            _verificar_conjuncao_where(condicao, escopo, texto, externos)


def _declarar_item(item, escopo, texto, externos):
    """Declara as tabelas de um item do FROM e valida as condições ON.

    Em SQL, a condição ON só enxerga as tabelas já unidas até aquele ponto,
    então ela é verificada logo após declarar o lado direito do JOIN.
    """
    if isinstance(item, Tabela):
        _declarar_tabela(item, escopo, texto)
        return {item.nome_visivel: item}
    locais = _declarar_item(item.esquerda, escopo, texto, externos)
    locais.update(_declarar_item(item.direita, escopo, texto, externos))
    subconsulta = _primeira_subconsulta(item.condicao)
    if subconsulta is not None:
        raise ErroSemantico('subconsultas não são aceitas na condição ON; '
                            'mova a condição para o WHERE', *_posicao(subconsulta, texto))
    _verificar_condicao(item.condicao, locais, texto, externos)
    return locais


def _declarar_tabela(tabela, escopo, texto):
    nome = tabela.nome_visivel
    if nome in escopo:
        raise ErroSemantico(
            f"a tabela '{nome}' aparece mais de uma vez no FROM; "
            f"use apelidos diferentes (ex.: {tabela.nome} t1, {tabela.nome} t2)",
            *_posicao(tabela, texto))
    escopo[nome] = tabela


# --- Subconsultas -----------------------------------------------------------


def _verificar_conjuncao_where(condicao, escopo, texto, externos):
    """Cada condição do WHERE ligada por AND pode conter uma subconsulta,
    na forma `operando op (SELECT ...)` ou `operando IN (SELECT ...)`.

    Essas formas viram semijunções. Dentro de OR ou NOT a tradução por
    semijunção mudaria o resultado, então não são aceitas.
    """
    if isinstance(condicao, Comparacao):
        subconsultas = [o for o in (condicao.esquerda, condicao.direita)
                        if isinstance(o, Subconsulta)]
        if len(subconsultas) == 2:
            raise ErroSemantico('comparação entre duas subconsultas não é suportada',
                                *_posicao(subconsultas[1], texto))
        if subconsultas:
            outro = (condicao.direita if subconsultas[0] is condicao.esquerda
                     else condicao.esquerda)
            _verificar_subconsulta(subconsultas[0], outro, escopo, texto, externos)
            return
    elif isinstance(condicao, Em):
        if condicao.negado:
            raise ErroSemantico('NOT IN com subconsulta não é suportado '
                                '(exigiria antijunção e tratamento de NULL)',
                                *_posicao(condicao.subconsulta, texto))
        if isinstance(condicao.operando, Subconsulta):
            raise ErroSemantico('uma subconsulta antes de IN não é suportada',
                                *_posicao(condicao.operando, texto))
        _verificar_subconsulta(condicao.subconsulta, condicao.operando, escopo, texto, externos)
        return
    elif isinstance(condicao, Existe):
        raise ErroSemantico('EXISTS não é suportado (em geral exige subconsulta correlacionada)',
                            *_posicao(condicao.subconsulta, texto))

    subconsulta = _primeira_subconsulta(condicao)
    if subconsulta is not None:
        raise ErroSemantico('subconsulta dentro de OR ou NOT não é suportada; ela só pode '
                            'aparecer em uma condição do WHERE ligada às demais por AND',
                            *_posicao(subconsulta, texto))
    _verificar_condicao(condicao, escopo, texto, externos)


def _verificar_subconsulta(subconsulta, outro, escopo, texto, externos):
    interna = subconsulta.consulta
    if interna.colunas is None or len(interna.colunas) != 1:
        raise ErroSemantico('a subconsulta precisa devolver exatamente uma coluna '
                            '(SELECT * e listas não são aceitos)', *_posicao(subconsulta, texto))
    analisar(interna, texto, externos + (escopo,))

    if isinstance(outro, Coluna):
        _verificar_coluna(outro, escopo, texto, externos)
        # Na semijunção as colunas dos dois lados ficam juntas na condição.
        # Com uma tabela só, o tradutor qualifica a coluna externa; com
        # várias, um nome igual ao da coluna da subconsulta seria ambíguo.
        coluna_interna = interna.colunas[0].nome
        if outro.tabela is None and len(escopo) > 1 and outro.nome == coluna_interna:
            raise ErroSemantico(
                f"'{outro.nome}' é ambíguo ao lado da subconsulta, que também devolve "
                f"'{coluna_interna}'; qualifique a coluna (ex.: tabela.{outro.nome})",
                *_posicao(outro, texto))


def _primeira_subconsulta(condicao):
    if isinstance(condicao, Comparacao):
        for operando in (condicao.esquerda, condicao.direita):
            if isinstance(operando, Subconsulta):
                return operando
        return None
    if isinstance(condicao, (E, Ou)):
        return (_primeira_subconsulta(condicao.esquerda)
                or _primeira_subconsulta(condicao.direita))
    if isinstance(condicao, Nao):
        return _primeira_subconsulta(condicao.operando)
    if isinstance(condicao, (Em, Existe)):
        return condicao.subconsulta
    return None


# --- Colunas ----------------------------------------------------------------


def _verificar_condicao(condicao, escopo, texto, externos):
    if isinstance(condicao, Comparacao):
        for operando in (condicao.esquerda, condicao.direita):
            if isinstance(operando, Coluna):
                _verificar_coluna(operando, escopo, texto, externos)
    elif isinstance(condicao, (E, Ou)):
        _verificar_condicao(condicao.esquerda, escopo, texto, externos)
        _verificar_condicao(condicao.direita, escopo, texto, externos)
    elif isinstance(condicao, Nao):
        _verificar_condicao(condicao.operando, escopo, texto, externos)


def _verificar_coluna(coluna, escopo, texto, externos):
    if coluna.tabela is None or coluna.tabela in escopo:
        return
    if any(coluna.tabela in externo for externo in externos):
        raise ErroSemantico(
            f"'{coluna}' referencia a tabela '{coluna.tabela}' da consulta externa; "
            "subconsultas correlacionadas não são suportadas", *_posicao(coluna, texto))
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
