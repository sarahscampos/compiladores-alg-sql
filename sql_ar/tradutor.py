# -*- coding: utf-8 -*-
# [NOVO] Arquivo criado neste trabalho; não existe no exemplo calc.py.
"""Fachada que encadeia as fases: léxica -> sintática -> semântica -> tradução."""
from dataclasses import dataclass

from . import algebra, grafo, otimizador, semantica
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
    valores: list = None                  # atributos dos filhos em cada redução

    @property
    def texto(self):
        return algebra.formatar(self.expressao)

    @property
    def expressao_otimizada(self):
        return otimizador.otimizar(self.expressao)

    @property
    def texto_otimizado(self):
        return algebra.formatar(self.expressao_otimizada)

    def arvore_algebra(self, otimizada=False):
        expressao = self.expressao_otimizada if otimizada else self.expressao
        return algebra.formatar_arvore(expressao)

    def salvar_grafo(self, caminho, otimizada=False):
        """Salva a árvore de consulta como um grafo em SVG."""
        expressao = self.expressao_otimizada if otimizada else self.expressao
        grafo.salvar_svg(expressao, caminho)

    def derivacao(self):
        return formatar_derivacao(self.reducoes)

    def arvore_derivacao(self):
        """Árvore de derivação com o atributo .val de cada não terminal."""
        return arvore_sintatica(self.reducoes, self.valores, self.consulta)

    def arvore_sintatica(self, anotada=False):
        return formatar_arvore_sintatica(self.arvore_derivacao(), anotada=anotada)

    def salvar_grafo_derivacao(self, caminho, anotada=False):
        """Salva a árvore de derivação (anotada ou não) como grafo em SVG."""
        grafo.salvar_svg_derivacao(self.arvore_derivacao(), caminho, anotada)


def traduzir(sql: str) -> ResultadoTraducao:
    """Traduz uma consulta SQL. Lança ErroLexico, ErroSintatico ou ErroSemantico."""
    parser = SqlParser()
    consulta = parser.analisar(sql)
    semantica.analisar(consulta, sql)
    return ResultadoTraducao(sql, consulta, algebra.traduzir(consulta),
                             parser.reducoes, parser.valores)


def listar_tokens(sql: str):
    """Somente a análise léxica: lista de (tipo, valor, linha)."""
    return [(t.type, t.value, t.lineno) for t in SqlLexer().tokenize(sql)]
