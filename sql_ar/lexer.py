# -*- coding: utf-8 -*-
"""Analisador léxico (SLY) para o subconjunto de SQL aceito pelo tradutor."""
from sly import Lexer

from .erros import ErroLexico, calcular_coluna

# Palavras-chave são reconhecidas primeiro como identificadores e depois
# reclassificadas. Comparar em maiúsculas torna o SQL case-insensitive.
PALAVRAS_RESERVADAS = {
    'SELECT': 'SELECT',
    'FROM': 'FROM',
    'WHERE': 'WHERE',
    'AND': 'AND',
    'OR': 'OR',
    'NOT': 'NOT',
    'JOIN': 'JOIN',
    'INNER': 'INNER',
    'ON': 'ON',
    'AS': 'AS',
}


class SqlLexer(Lexer):
    # Conjunto de tokens (terminais da gramática)
    tokens = {
        SELECT, FROM, WHERE, AND, OR, NOT, JOIN, INNER, ON, AS,
        ID, NUMBER, STRING,
        COMMA, DOT, STAR, SEMI, LPAREN, RPAREN,
        EQ, NE, LT, GT, LE, GE,
    }

    # Espaços, tabulações e '\r' são descartados
    ignore = ' \t\r'

    # Comentários de linha no estilo SQL: -- até o fim da linha
    ignore_comment = r'--[^\n]*'

    # Operadores relacionais: os de dois caracteres vêm antes dos de um,
    # pois o SLY testa os padrões na ordem em que são definidos.
    LE = r'<='
    GE = r'>='
    NE = r'!=|<>'
    LT = r'<'
    GT = r'>'
    EQ = r'='

    # Pontuação
    COMMA  = r','
    DOT    = r'\.'
    STAR   = r'\*'
    SEMI   = r';'
    LPAREN = r'\('
    RPAREN = r'\)'

    # Texto entre aspas simples; '' dentro do texto representa uma aspa
    @_(r"'(?:[^'\n]|'')*'")
    def STRING(self, t):
        t.value = t.value[1:-1].replace("''", "'")
        return t

    # Números inteiros ou decimais (o lexema é mantido como texto
    # para que a saída reproduza exatamente o que foi digitado)
    @_(r'\d+(?:\.\d+)?')
    def NUMBER(self, t):
        return t

    # Identificadores e palavras-chave
    @_(r'[A-Za-z_][A-Za-z0-9_]*')
    def ID(self, t):
        reservada = PALAVRAS_RESERVADAS.get(t.value.upper())
        if reservada:
            t.type = reservada
            t.value = t.value.upper()
        return t

    # Contagem de linhas
    @_(r'\n+')
    def ignore_newline(self, t):
        self.lineno += len(t.value)

    # Tratamento de erros léxicos (caracteres que não iniciam nenhum token)
    def error(self, t):
        caractere = t.value[0]
        coluna = calcular_coluna(self.text, t.index)
        if caractere == "'":
            mensagem = 'texto entre aspas simples não foi fechado'
        else:
            mensagem = f'caractere inválido {caractere!r}'
        raise ErroLexico(mensagem, self.lineno, coluna)
