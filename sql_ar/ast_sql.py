# -*- coding: utf-8 -*-
"""Árvore sintática abstrata (AST) da consulta SQL.

Estes nós são produzidos pelas ações semânticas do parser. Eles registram
apenas a estrutura lógica da consulta, sem detalhes de pontuação.
"""
from dataclasses import dataclass, field
from typing import Optional, Union


# --- Operandos -----------------------------------------------------------

@dataclass(frozen=True)
class Coluna:
    """Referência a coluna: simples (nome) ou qualificada (tabela.nome)."""
    nome: str
    tabela: Optional[str] = None
    # Posição no texto, usada só em mensagens de erro semântico
    linha: Optional[int] = field(default=None, compare=False)
    indice: Optional[int] = field(default=None, compare=False)

    def __str__(self):
        return f'{self.tabela}.{self.nome}' if self.tabela else self.nome


@dataclass(frozen=True)
class Numero:
    lexema: str

    def __str__(self):
        return self.lexema


@dataclass(frozen=True)
class Texto:
    valor: str

    def __str__(self):
        return "'" + self.valor.replace("'", "''") + "'"


@dataclass(frozen=True)
class Subconsulta:
    """( SELECT ... ) usada como operando ou após IN / EXISTS."""
    consulta: 'Consulta'
    linha: Optional[int] = field(default=None, compare=False)
    indice: Optional[int] = field(default=None, compare=False)

    def __str__(self):
        return '(SELECT ...)'


Operando = Union[Coluna, Numero, Texto, Subconsulta]


# --- Condições (WHERE e ON) ----------------------------------------------

@dataclass(frozen=True)
class Comparacao:
    esquerda: Operando
    operador: str
    direita: Operando


@dataclass(frozen=True)
class E:
    esquerda: 'Condicao'
    direita: 'Condicao'


@dataclass(frozen=True)
class Ou:
    esquerda: 'Condicao'
    direita: 'Condicao'


@dataclass(frozen=True)
class Nao:
    operando: 'Condicao'


@dataclass(frozen=True)
class Em:
    """operando IN (subconsulta), ou NOT IN quando negado."""
    operando: Operando
    subconsulta: Subconsulta
    negado: bool = False


@dataclass(frozen=True)
class Existe:
    """EXISTS (subconsulta)"""
    subconsulta: Subconsulta


Condicao = Union[Comparacao, E, Ou, Nao, Em, Existe]


def separar_conjuncoes(condicao):
    """c1 AND (c2 AND c3)  ->  [c1, c2, c3]"""
    if isinstance(condicao, E):
        return separar_conjuncoes(condicao.esquerda) + separar_conjuncoes(condicao.direita)
    return [condicao]


# --- Cláusula FROM -------------------------------------------------------

@dataclass(frozen=True)
class Tabela:
    nome: str
    apelido: Optional[str] = None
    linha: Optional[int] = field(default=None, compare=False)
    indice: Optional[int] = field(default=None, compare=False)

    @property
    def nome_visivel(self):
        """Nome pelo qual a tabela é referenciada no restante da consulta."""
        return self.apelido or self.nome


@dataclass(frozen=True)
class Join:
    """item_from JOIN tabela ON condicao"""
    esquerda: Union[Tabela, 'Join']
    direita: Tabela
    condicao: Condicao


ItemFrom = Union[Tabela, Join]


# --- Consulta ------------------------------------------------------------

@dataclass(frozen=True)
class Consulta:
    # None representa SELECT * (todas as colunas)
    colunas: Optional[tuple]
    origem: tuple
    where: Optional[Condicao] = None
