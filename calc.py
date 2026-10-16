# -*- coding: utf-8 -*-
from sly import Lexer, Parser


class CalcLexer(Lexer):
    # Conjunto de tokens que o analisador léxico vai identificar
    tokens = { NUMBER, PLUS, MINUS, TIMES, DIVIDE, LPAREN, RPAREN }

    # Expressões regulares para tokens simples
    PLUS   = r'\+'
    MINUS  = r'-'
    TIMES  = r'\*'
    DIVIDE = r'/'
    LPAREN = r'\('
    RPAREN = r'\)'

    # Expressão regular para números (converte automaticamente para float ou int)
    @_(r'\d+(\.\d+)?')
    def NUMBER(self, t):
        if '.' in t.value:
            t.value = float(t.value)
        else:
            t.value = int(t.value)
        return t

    # Ignorar espaços em branco e tabulações
    ignore = ' \t'

    # Controle e contagem de quebra de linhas
    @_(r'\n+')
    def ignore_newline(self, t):
        self.lineno += t.value.count('\n')

    # Tratamento de erros léxicos (caracteres desconhecidos)
    def error(self, t):
        print(f"Caractere inválido: '{t.value[0]}' na linha {self.lineno}")
        self.index += 1

class CalcParser(Parser):
    # Recebe a lista de tokens vindos do Lexer
    tokens = CalcLexer.tokens

    # Definição de precedência e associatividade (evita a ambiguidade da gramática)
    precedence = (
        ('left', PLUS, MINUS),
        ('left', TIMES, DIVIDE),
        ('right', UMINUS), # Menos unário, ex: -5 ou -(2+3)
    )

    # --- Regras Gramaticais e Ações Sintáticas ---

    @_('expr')
    def statement(self, p):
        return p.expr

    @_('expr PLUS expr')
    def expr(self, p):
        return p.expr0 + p.expr1

    @_('expr MINUS expr')
    def expr(self, p):
        return p.expr0 - p.expr1

    @_('expr TIMES expr')
    def expr(self, p):
        return p.expr0 * p.expr1

    @_('expr DIVIDE expr')
    def expr(self, p):
        if p.expr1 == 0:
            print("Erro: Divisão por zero!")
            return 0
        return p.expr0 / p.expr1

    @_('MINUS expr %prec UMINUS')
    def expr(self, p):
        return -p.expr

    @_('LPAREN expr RPAREN')
    def expr(self, p):
        return p.expr

    @_('NUMBER')
    def expr(self, p):
        return p.NUMBER

    # Tratamento de erros sintáticos (expressões mal formadas)
    def error(self, p):
        if p:
            print(f"Erro de sintaxe próximo ao token '{p.value}' na linha {p.lineno}")
        else:
            print("Erro de sintaxe no final da expressão.")

if __name__ == '__main__':
    lexer = CalcLexer()
    parser = CalcParser()
    
    print("--- Calculadora Aritmética com SLY (Python) ---")
    print("Digite a expressão ou 'sair' para encerrar.")
    
    while True:
        try:
            text = input('calc > ')
            if text.strip().lower() == 'sair':
                break
            if not text.strip():
                continue
            
            # Gera os tokens e faz o parsing executando a expressão
            result = parser.parse(lexer.tokenize(text))
            if result is not None:
                print(f"Resultado: {result}")
        except Exception as e:
            print(f"Erro ao processar: {e}")
