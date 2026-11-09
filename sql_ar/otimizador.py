# -*- coding: utf-8 -*-
# [NOVO] Arquivo criado neste trabalho; não existe no exemplo calc.py.
"""Otimização algébrica (heurística) da árvore de consulta.

Recebe a forma canônica  π_{L}(σ_{C}(R1 × ... × Rn))  e devolve uma árvore
equivalente que descarta linhas e colunas o mais cedo possível:

1. Cascata de seleções: σ_{c1 ∧ c2} é separada em c1 e c2.
2. Seleções descem até a subárvore que contém todas as tabelas citadas.
3. Uma condição que liga os dois lados de um × transforma-o em ⋈.
4. Projeções descem, mantendo só as colunas usadas acima de cada ponto.

Sem o esquema do banco não se sabe a qual tabela pertence uma coluna não
qualificada. Por isso a condição que usa uma delas não desce, e uma consulta
com várias tabelas que use alguma não recebe projeções intermediárias.
A ordem das tabelas no FROM é mantida: não há reordenação de junções.

Numa semijunção R ⋉ S só as colunas de R continuam acima dela. As regras
valem para R; a subconsulta S é otimizada separadamente.
"""
from dataclasses import replace
from functools import reduce

from .algebra import (BINARIOS, Juncao, ProdutoCartesiano, Projecao, Relacao,
                      Renomeacao, Selecao, Semijuncao)
from .ast_sql import Coluna, Comparacao, E, Nao, Ou


def otimizar(expressao):
    expressao = _otimizar_subconsultas(expressao)
    # Com uma só tabela não há para onde descer: a forma canônica já é a melhor
    if _contar_relacoes(expressao) < 2:
        return expressao

    if isinstance(expressao, Projecao):
        atributos, corpo = expressao.atributos, expressao.expressao
    else:
        # SELECT * precisa de todas as colunas: não há projeção a descer
        atributos, corpo = None, expressao

    corpo = _empurrar_selecoes(corpo)
    if atributos is None:
        return corpo
    if _projecoes_sao_seguras(atributos, corpo):
        corpo = _remover_projecao_redundante(_restringir(corpo, list(atributos)), atributos)
    return Projecao(atributos, corpo)


# --- Regras 1 a 3: seleções ------------------------------------------------


def _empurrar_selecoes(corpo):
    condicoes = []
    if isinstance(corpo, Selecao):
        condicoes, corpo = _separar_conjuncoes(corpo.condicao), corpo.expressao
    # Condições sem dono conhecido ficam acima de todas as tabelas
    pendentes = [c for c in condicoes if not _totalmente_qualificada(c)]
    colocaveis = [c for c in condicoes if _totalmente_qualificada(c)]
    return _abaixo_das_semijuncoes(_inserir(corpo, colocaveis), pendentes)


def _abaixo_das_semijuncoes(expressao, condicoes):
    """σ_c(R ⋉ S) = σ_c(R) ⋉ S para qualquer c, pois acima da semijunção só
    existem as colunas de R. Vale até para colunas sem tabela."""
    if isinstance(expressao, Semijuncao):
        return replace(expressao,
                       esquerda=_abaixo_das_semijuncoes(expressao.esquerda, condicoes))
    return _aplicar_selecao(expressao, condicoes)


def _inserir(expressao, condicoes):
    """Coloca cada condição no ponto mais baixo em que ela pode ser avaliada."""
    if isinstance(expressao, Semijuncao):
        # Acima de R ⋉ S só há colunas de R: tudo desce para a esquerda,
        # e a condição da semijunção fica onde está.
        return replace(expressao, esquerda=_inserir(expressao.esquerda, condicoes))
    if not isinstance(expressao, BINARIOS):
        return _aplicar_selecao(expressao, condicoes)

    proprias = []
    if isinstance(expressao, Juncao):
        proprias = _separar_conjuncoes(expressao.condicao)
    nomes_esquerda = _tabelas_visiveis(expressao.esquerda)
    nomes_direita = _tabelas_visiveis(expressao.direita)

    esquerda, direita, ponte = [], [], []
    for condicao in proprias + condicoes:
        tabelas = {c.tabela for c in _colunas(condicao)}
        if _totalmente_qualificada(condicao) and tabelas <= nomes_esquerda:
            esquerda.append(condicao)
        elif _totalmente_qualificada(condicao) and tabelas <= nomes_direita:
            direita.append(condicao)
        else:
            ponte.append(condicao)

    novo_esquerda = _inserir(expressao.esquerda, esquerda)
    novo_direita = _inserir(expressao.direita, direita)
    if ponte:
        return Juncao(novo_esquerda, novo_direita, _combinar(ponte))
    return ProdutoCartesiano(novo_esquerda, novo_direita)


def _aplicar_selecao(expressao, condicoes):
    return Selecao(_combinar(condicoes), expressao) if condicoes else expressao


def _separar_conjuncoes(condicao):
    if isinstance(condicao, E):
        return _separar_conjuncoes(condicao.esquerda) + _separar_conjuncoes(condicao.direita)
    return [condicao]


def _combinar(condicoes):
    return reduce(E, condicoes)


# --- Regra 4: projeções ----------------------------------------------------


def _restringir(expressao, necessarias):
    """Faz a subárvore produzir só as colunas `necessarias` (todas dela)."""
    if isinstance(expressao, Semijuncao):
        da_condicao = _da_subarvore(_colunas(expressao.condicao), expressao.esquerda)
        usadas = list(dict.fromkeys(necessarias + da_condicao))
        nova = replace(expressao, esquerda=_restringir(expressao.esquerda, usadas))
        return _aplicar_projecao(nova, necessarias) if set(da_condicao) - set(necessarias) else nova
    if not isinstance(expressao, BINARIOS):
        return _aplicar_projecao(expressao, necessarias)

    da_juncao = []
    if isinstance(expressao, Juncao):
        da_juncao = _colunas(expressao.condicao)
    # dict.fromkeys tira as repetidas mantendo a ordem de aparecimento
    usadas = list(dict.fromkeys(necessarias + da_juncao))

    esquerda = _restringir(expressao.esquerda, _da_subarvore(usadas, expressao.esquerda))
    direita = _restringir(expressao.direita, _da_subarvore(usadas, expressao.direita))
    if isinstance(expressao, ProdutoCartesiano):
        return ProdutoCartesiano(esquerda, direita)

    nova = Juncao(esquerda, direita, expressao.condicao)
    # A coluna usada só na condição da junção pode ser descartada logo depois
    return _aplicar_projecao(nova, necessarias) if set(da_juncao) - set(necessarias) else nova


def _aplicar_projecao(expressao, colunas):
    # Sem colunas a projeção não existe: a tabela sem colunas usadas ainda
    # influencia o resultado (um × com tabela vazia dá vazio), então fica.
    return Projecao(tuple(colunas), expressao) if colunas else expressao


def _da_subarvore(colunas, expressao):
    nomes = _tabelas_visiveis(expressao)
    return [c for c in colunas if c.tabela in nomes]


def _remover_projecao_redundante(corpo, atributos):
    # π_{L}(π_{L}(x)) = π_{L}(x)
    if isinstance(corpo, Projecao) and set(corpo.atributos) == set(atributos):
        return corpo.expressao
    return corpo


def _projecoes_sao_seguras(atributos, expressao):
    colunas = list(atributos) + _colunas_das_condicoes(expressao)
    return all(c.tabela is not None for c in colunas)


def _colunas_das_condicoes(expressao):
    if isinstance(expressao, Selecao):
        return _colunas(expressao.condicao) + _colunas_das_condicoes(expressao.expressao)
    if isinstance(expressao, Semijuncao):
        # As condições internas da subconsulta não dizem respeito a este nível
        return _colunas(expressao.condicao) + _colunas_das_condicoes(expressao.esquerda)
    if isinstance(expressao, BINARIOS):
        proprias = _colunas(expressao.condicao) if isinstance(expressao, Juncao) else []
        return (proprias + _colunas_das_condicoes(expressao.esquerda)
                + _colunas_das_condicoes(expressao.direita))
    return []


# --- Subconsultas ----------------------------------------------------------


def _otimizar_subconsultas(expressao):
    """Otimiza cada subconsulta (lado direito das semijunções) por conta própria."""
    if isinstance(expressao, Semijuncao):
        subconsulta = expressao.direita   # ρ_{apelido}(consulta interna)
        return replace(expressao,
                       esquerda=_otimizar_subconsultas(expressao.esquerda),
                       direita=replace(subconsulta, expressao=otimizar(subconsulta.expressao)))
    if isinstance(expressao, BINARIOS):
        return replace(expressao,
                       esquerda=_otimizar_subconsultas(expressao.esquerda),
                       direita=_otimizar_subconsultas(expressao.direita))
    if isinstance(expressao, (Selecao, Projecao)):
        return replace(expressao, expressao=_otimizar_subconsultas(expressao.expressao))
    return expressao


# --- Consultas sobre a árvore ----------------------------------------------


def _contar_relacoes(expressao):
    if isinstance(expressao, Relacao):
        return 1
    if isinstance(expressao, BINARIOS):
        return _contar_relacoes(expressao.esquerda) + _contar_relacoes(expressao.direita)
    return _contar_relacoes(expressao.expressao)



def _tabelas_visiveis(expressao):
    """Nomes pelos quais as tabelas da subárvore podem ser referenciadas."""
    if isinstance(expressao, Relacao):
        return {expressao.nome}
    if isinstance(expressao, Renomeacao):
        return {expressao.novo_nome}
    if isinstance(expressao, Semijuncao):
        return _tabelas_visiveis(expressao.esquerda)
    if isinstance(expressao, BINARIOS):
        return _tabelas_visiveis(expressao.esquerda) | _tabelas_visiveis(expressao.direita)
    return _tabelas_visiveis(expressao.expressao)


def _colunas(condicao):
    if isinstance(condicao, Comparacao):
        return [o for o in (condicao.esquerda, condicao.direita) if isinstance(o, Coluna)]
    if isinstance(condicao, (E, Ou)):
        return _colunas(condicao.esquerda) + _colunas(condicao.direita)
    if isinstance(condicao, Nao):
        return _colunas(condicao.operando)
    raise TypeError(f'condição desconhecida: {condicao!r}')


def _totalmente_qualificada(condicao):
    """Só é possível decidir onde a condição vai se ela citar colunas e
    todas tiverem tabela. `1 = 1` não cita nenhuma e fica onde está."""
    colunas = _colunas(condicao)
    return bool(colunas) and all(c.tabela is not None for c in colunas)
