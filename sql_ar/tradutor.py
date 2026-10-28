# -*- coding: utf-8 -*-
"""Fachada que encadeia as fases: léxica -> sintática -> semântica -> tradução."""
from dataclasses import dataclass

from . import algebra, semantica
from .ast_sql import Consulta
from .derivacao import (arvore_sintatica, formatar_arvore_sintatica,
                        formatar_derivacao)
from .lexer import SqlLexer
from .parser import SqlParser


@dataclass
class ResultadoTraducao:
    sql: str
    consulta: Consulta                    # AST SQL
    expressao: algebra.ExprRelacional     # árvore da Álgebra Relacional
    reducoes: list                        # reduções feitas pelo parser LR

    @property
    def texto(self):
        return algebra.formatar(self.expressao)

    def arvore_algebra(self):
        return algebra.formatar_arvore(self.expressao)

    def derivacao(self):
        return formatar_derivacao(self.reducoes)

    def arvore_sintatica(self):
        return formatar_arvore_sintatica(arvore_sintatica(self.reducoes))


def traduzir(sql: str) -> ResultadoTraducao:
    """Traduz uma consulta SQL. Lança ErroLexico, ErroSintatico ou ErroSemantico."""
    parser = SqlParser()
    consulta = parser.analisar(sql)
    semantica.analisar(consulta, sql)
    return ResultadoTraducao(sql, consulta, algebra.traduzir(consulta), parser.reducoes)


def listar_tokens(sql: str):
    """Somente a análise léxica: lista de (tipo, valor, linha)."""
    return [(t.type, t.value, t.lineno) for t in SqlLexer().tokenize(sql)]
