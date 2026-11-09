# -*- coding: utf-8 -*-
"""Analisador léxico (SLY) para o subconjunto de SQL aceito pelo tradutor.

[MODIFICADO] Baseado no CalcLexer do calc.py. As marcas [NOVO] e
[MODIFICADO] indicam o que mudou em relação a ele.
"""
from sly import Lexer

from .erros import ErroLexico, calcular_coluna

# [NOVO] Palavras-chave são reconhecidas primeiro como identificadores e depois
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
    'IN': 'IN',
    'EXISTS': 'EXISTS',
}


class SqlLexer(Lexer):
    # [MODIFICADO] Conjunto de tokens (terminais da gramática): os do SQL no
    # lugar de NUMBER, PLUS, MINUS, TIMES, DIVIDE, LPAREN e RPAREN do calc.py.
    tokens = {
        SELECT, FROM, WHERE, AND, OR, NOT, JOIN, INNER, ON, AS, IN, EXISTS,
        ID, NUMBER, STRING,
        COMMA, DOT, STAR, SEMI, LPAREN, RPAREN,
        EQ, NE, LT, GT, LE, GE,
    }

    # Espaços, tabulações e '\r' são descartados
    ignore = ' \t\r'

    # [NOVO] Comentários de linha no estilo SQL: -- até o fim da linha
    ignore_comment = r'--[^\n]*'

    # [NOVO] Operadores relacionais: os de dois caracteres vêm antes dos de um,
    # pois o SLY testa os padrões na ordem em que são definidos.
    LE = r'<='
    GE = r'>='
    NE = r'!=|<>'
    LT = r'<'
    GT = r'>'
    EQ = r'='

    # [MODIFICADO] Pontuação: só LPAREN e RPAREN existiam no calc.py
    COMMA  = r','
    DOT    = r'\.'
    STAR   = r'\*'
    SEMI   = r';'
    LPAREN = r'\('
    RPAREN = r'\)'

    # [NOVO] Texto entre aspas simples; '' dentro do texto representa uma aspa
    @_(r"'(?:[^'\n]|'')*'")
    def STRING(self, t):
        t.value = t.value[1:-1].replace("''", "'")
        return t

    # [MODIFICADO] Números inteiros ou decimais. O calc.py convertia para
    # int/float; aqui o lexema é mantido como texto, para que a saída
    # reproduza exatamente o que foi digitado.
    @_(r'\d+(?:\.\d+)?')
    def NUMBER(self, t):
        return t

    # [NOVO] Identificadores e palavras-chave
    @_(r'[A-Za-z_][A-Za-z0-9_]*')
    def ID(self, t):
        reservada = PALAVRAS_RESERVADAS.get(t.value.upper())
        if reservada:
            t.type = reservada
            t.value = t.value.upper()
        return t

    # Contagem de linhas (igual ao calc.py)
    @_(r'\n+')
    def ignore_newline(self, t):
        self.lineno += len(t.value)

    # [MODIFICADO] Tratamento de erros léxicos. O calc.py imprimia e pulava o
    # caractere; aqui a análise para com linha, coluna e uma mensagem específica.
    def error(self, t):
        caractere = t.value[0]
        coluna = calcular_coluna(self.text, t.index)
        if caractere == "'":
            mensagem = 'texto entre aspas simples não foi fechado'
        else:
            mensagem = f'caractere inválido {caractere!r}'
        raise ErroLexico(mensagem, self.lineno, coluna)
