# -*- coding: utf-8 -*-
"""Interface de linha de comando do tradutor SQL -> Álgebra Relacional.

Uso:
    python main.py                       # modo interativo
    python main.py "SELECT nome FROM alunos;"
    python main.py -f consultas.sql      # uma ou mais consultas terminadas em ';'
    python main.py --exemplos            # executa os exemplos do README
Opções: --tokens  --arvore  --derivacao
"""
import argparse
import sys

from sql_ar import ErroTraducao, listar_tokens, traduzir

EXEMPLOS = [
    'SELECT nome FROM alunos;',
    'SELECT nome, idade, curso FROM alunos;',
    'SELECT nome, idade FROM alunos WHERE idade >= 18;',
    "SELECT nome FROM alunos WHERE idade >= 18 AND curso = 'Computação';",
    "SELECT nome FROM alunos WHERE (curso = 'Computação' OR curso = 'Física') AND idade < 30;",
    'SELECT alunos.nome, matriculas.disciplina FROM alunos, matriculas '
    'WHERE alunos.id = matriculas.aluno_id;',
    'SELECT a.nome, m.nota FROM alunos a JOIN matriculas m ON a.id = m.aluno_id '
    'WHERE m.nota > 7;',
    'SELECT nome idade FROM alunos;',
]


def mostrar(sql, opcoes):
    print(f'\nSQL: {" ".join(sql.split())}')
    try:
        if opcoes.tokens:
            print('Tokens:')
            for tipo, valor, linha in listar_tokens(sql):
                print(f'    {tipo:<7} {valor!r}  (linha {linha})')
        resultado = traduzir(sql)
    except ErroTraducao as erro:
        print(erro.destacar(sql))
        return False

    print(f'AR:  {resultado.texto}')
    if opcoes.arvore:
        print('Árvore da Álgebra Relacional:')
        print(_indentar(resultado.arvore_algebra()))
        print('Árvore sintática:')
        print(_indentar(resultado.arvore_sintatica()))
    if opcoes.derivacao:
        print('Derivação mais à direita:')
        print(resultado.derivacao())
    return True


def separar_consultas(texto):
    """Divide um arquivo em consultas pelo ';' final de cada uma.

    Isto é só um utilitário de entrada: cada consulta continua sendo
    analisada inteiramente pelo lexer/parser SLY (incluindo o ';').
    """
    consultas, atual = [], []
    for linha in texto.splitlines():
        atual.append(linha)
        if linha.rstrip().endswith(';'):
            consultas.append('\n'.join(atual))
            atual = []
    if '\n'.join(atual).strip():
        consultas.append('\n'.join(atual))
    return consultas


def modo_interativo(opcoes):
    print('--- Tradutor SQL -> Álgebra Relacional (SLY) ---')
    print('Digite a consulta (pode usar várias linhas; termine com ";" ou linha vazia).')
    print('Comandos: :tokens  :arvore  :derivacao  (liga/desliga)  :exemplos  :sair')
    while True:
        try:
            linhas = []
            while True:
                linha = input('sql> ' if not linhas else '...> ')
                if not linhas and linha.strip().startswith(':'):
                    linhas = [linha.strip()]
                    break
                if not linha.strip():
                    break
                linhas.append(linha)
                if linha.rstrip().endswith(';'):
                    break
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not linhas:
            continue
        comando = linhas[0].lower()
        if comando in (':sair', ':q', 'sair'):
            break
        if comando in (':tokens', ':arvore', ':derivacao'):
            nome = comando[1:]
            setattr(opcoes, nome, not getattr(opcoes, nome))
            print(f'{nome}: {"ligado" if getattr(opcoes, nome) else "desligado"}')
            continue
        if comando == ':exemplos':
            for sql in EXEMPLOS:
                mostrar(sql, opcoes)
            continue
        mostrar('\n'.join(linhas), opcoes)


def main(argv=None):
    # Garante que σ, π, ⋈ etc. apareçam corretamente no console do Windows
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    ap = argparse.ArgumentParser(description='Traduz consultas SQL para Álgebra Relacional.')
    ap.add_argument('consulta', nargs='?', help='consulta SQL (entre aspas)')
    ap.add_argument('-f', '--arquivo', help='arquivo com consultas terminadas em ";"')
    ap.add_argument('--exemplos', action='store_true', help='executa as consultas de exemplo')
    ap.add_argument('--tokens', action='store_true', help='mostra os tokens')
    ap.add_argument('--arvore', action='store_true', help='mostra as árvores')
    ap.add_argument('--derivacao', action='store_true', help='mostra a derivação mais à direita')
    opcoes = ap.parse_args(argv)

    if opcoes.exemplos:
        consultas = EXEMPLOS
    elif opcoes.arquivo:
        with open(opcoes.arquivo, encoding='utf-8') as arq:
            consultas = separar_consultas(arq.read())
    elif opcoes.consulta is not None:
        consultas = [opcoes.consulta]
    else:
        modo_interativo(opcoes)
        return 0

    sucesso = [mostrar(sql, opcoes) for sql in consultas]
    return 0 if all(sucesso) or opcoes.exemplos else 1


def _indentar(texto):
    return '\n'.join('    ' + linha for linha in texto.splitlines())


if __name__ == '__main__':
    sys.exit(main())
