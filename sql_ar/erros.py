# -*- coding: utf-8 -*-
"""Exceções usadas pelas fases do tradutor (léxica, sintática e semântica)."""


def calcular_coluna(texto, indice):
    """Converte um índice absoluto do texto em coluna (começando em 1)."""
    inicio_linha = texto.rfind('\n', 0, indice) + 1
    return indice - inicio_linha + 1


class ErroTraducao(Exception):
    """Classe base: guarda a mensagem e a posição (linha/coluna) do erro."""

    tipo = 'Erro'

    def __init__(self, mensagem, linha=None, coluna=None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.linha = linha
        self.coluna = coluna

    def __str__(self):
        if self.linha is not None and self.coluna is not None:
            return f'{self.tipo} (linha {self.linha}, coluna {self.coluna}): {self.mensagem}'
        return f'{self.tipo}: {self.mensagem}'

    def destacar(self, fonte):
        """Mostra a linha da consulta onde o erro ocorreu com um '^' embaixo."""
        if self.linha is None or self.coluna is None:
            return str(self)
        linhas = fonte.split('\n')
        if not 1 <= self.linha <= len(linhas):
            return str(self)
        trecho = linhas[self.linha - 1]
        marcador = ' ' * (self.coluna - 1) + '^'
        return f'{self}\n    {trecho}\n    {marcador}'


class ErroLexico(ErroTraducao):
    tipo = 'Erro léxico'


class ErroSintatico(ErroTraducao):
    tipo = 'Erro sintático'


class ErroSemantico(ErroTraducao):
    tipo = 'Erro semântico'
