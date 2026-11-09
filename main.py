# -*- coding: utf-8 -*-
"""Interface de linha de comando do tradutor SQL -> Álgebra Relacional.

Uso:
    python main.py                       # modo interativo
    python main.py "SELECT nome FROM alunos;"
    python main.py -f consultas.sql      # uma ou mais consultas terminadas em ';'
    python main.py --exemplos            # executa os exemplos do README
Opções: --tokens  --arvore  --anotada  --derivacao  --otimizar  --grafo ARQUIVO.svg
        --grafo-derivacao ARQUIVO.svg  --abrir  --producoes

[MODIFICADO] O laço interativo veio do calc.py (input -> parse -> imprime);
as opções, a leitura de arquivo e os grafos são novos.
"""
import argparse
import os
import sys
import webbrowser
from pathlib import Path

from sql_ar import ErroTraducao, listar_tokens, traduzir
from sql_ar.parser import tabela_producoes

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
    'SELECT nome FROM alunos WHERE idade > (SELECT idade FROM alunos WHERE id = 1);',
    'SELECT nome idade FROM alunos;',
]

ARQUIVO_GRAFO_PADRAO = 'arvore_consulta.svg'


def mostrar(sql, opcoes, numero=None):
    """`numero` é usado para numerar os arquivos quando há várias consultas."""
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
    if opcoes.otimizar:
        print(f'AR otimizada: {resultado.texto_otimizado}')
    if opcoes.arvore:
        print('Árvore da Álgebra Relacional:')
        print(_indentar(resultado.arvore_algebra()))
        if opcoes.otimizar:
            print('Árvore otimizada:')
            print(_indentar(resultado.arvore_algebra(otimizada=True)))
        print('Árvore de derivação (sintática):')
        print(_indentar(resultado.arvore_sintatica()))
    if opcoes.anotada:
        print('Árvore de derivação anotada (atributo .val de cada não terminal):')
        print(_indentar(resultado.arvore_sintatica(anotada=True)))
    if opcoes.derivacao:
        print('Derivação mais à direita:')
        print(resultado.derivacao())
    if opcoes.grafo:
        caminho = _numerar(opcoes.grafo, numero)
        salvar_grafo(resultado.salvar_grafo, caminho, opcoes.abrir)
        # A canônica e a otimizada ficam em dois arquivos, para comparar
        if opcoes.otimizar:
            salvar_grafo(resultado.salvar_grafo, caminho_otimizado(caminho), opcoes.abrir,
                         otimizada=True)
    if opcoes.grafo_derivacao:
        # A árvore de derivação e a anotada também ficam em dois arquivos
        caminho = _numerar(opcoes.grafo_derivacao, numero)
        salvar_grafo(resultado.salvar_grafo_derivacao, caminho, opcoes.abrir)
        salvar_grafo(resultado.salvar_grafo_derivacao, caminho_anotado(caminho), opcoes.abrir,
                     anotada=True)
    return True


def salvar_grafo(salvar, caminho, abrir, **opcoes):
    try:
        salvar(caminho, **opcoes)
    except OSError as erro:
        print(f'Não foi possível salvar o grafo em {caminho}: {erro}')
        return
    print(f'Grafo: {caminho}')
    if abrir:
        webbrowser.open(Path(caminho).resolve().as_uri())


def caminho_numerado(caminho, numero):
    """arvore.svg -> arvore_2.svg, para quando há várias consultas."""
    base, extensao = os.path.splitext(caminho)
    return f'{base}_{numero}{extensao}'


def caminho_otimizado(caminho):
    """arvore.svg -> arvore_otimizada.svg"""
    base, extensao = os.path.splitext(caminho)
    return f'{base}_otimizada{extensao}'


def caminho_anotado(caminho):
    """derivacao.svg -> derivacao_anotada.svg"""
    base, extensao = os.path.splitext(caminho)
    return f'{base}_anotada{extensao}'


def _numerar(caminho, numero):
    return caminho_numerado(caminho, numero) if numero is not None else caminho


def imprimir_producoes():
    """Tabela de produções e ações semânticas (item 4c do trabalho)."""
    largura = max(len(producao) for _, producao, _ in tabela_producoes())
    print(f'{"Nº":>3}  {"Produção":<{largura}}  Regra semântica')
    for numero, producao, regra in tabela_producoes():
        print(f'{numero:>3}  {producao:<{largura}}  {regra}')


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
    print('Comandos: :tokens  :arvore  :anotada  :derivacao  :otimizar  :grafo  (liga/desliga)')
    print('          :producoes  :exemplos  :sair')
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
        if comando in (':tokens', ':arvore', ':anotada', ':derivacao', ':otimizar'):
            nome = comando[1:]
            setattr(opcoes, nome, not getattr(opcoes, nome))
            print(f'{nome}: {"ligado" if getattr(opcoes, nome) else "desligado"}')
            continue
        if comando == ':grafo':
            opcoes.grafo = None if opcoes.grafo else ARQUIVO_GRAFO_PADRAO
            print(f'grafo: {opcoes.grafo or "desligado"}')
            continue
        if comando == ':producoes':
            imprimir_producoes()
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
    ap.add_argument('--arvore', action='store_true',
                    help='mostra a árvore relacional e a árvore de derivação')
    ap.add_argument('--anotada', action='store_true',
                    help='mostra a árvore de derivação anotada com os atributos')
    ap.add_argument('--derivacao', action='store_true', help='mostra a derivação mais à direita')
    ap.add_argument('--otimizar', action='store_true',
                    help='mostra também a árvore otimizada (seleções e projeções descem)')
    ap.add_argument('--grafo', metavar='ARQUIVO.svg',
                    help='salva a árvore de consulta como grafo em SVG')
    ap.add_argument('--grafo-derivacao', metavar='ARQUIVO.svg',
                    help='salva a árvore de derivação e a anotada (ARQUIVO_anotada.svg) em SVG')
    ap.add_argument('--abrir', action='store_true', help='abre os grafos salvos no navegador')
    ap.add_argument('--producoes', action='store_true',
                    help='mostra a tabela de produções e regras semânticas')
    opcoes = ap.parse_args(argv)
    if opcoes.abrir and not opcoes.grafo and not opcoes.grafo_derivacao:
        opcoes.grafo = ARQUIVO_GRAFO_PADRAO

    if opcoes.producoes:
        imprimir_producoes()
        if opcoes.consulta is None and not opcoes.arquivo and not opcoes.exemplos:
            return 0

    if opcoes.exemplos:
        consultas = EXEMPLOS
    elif opcoes.arquivo:
        # utf-8-sig aceita o BOM que editores e o PowerShell gravam no Windows
        with open(opcoes.arquivo, encoding='utf-8-sig') as arq:
            consultas = separar_consultas(arq.read())
    elif opcoes.consulta is not None:
        consultas = [opcoes.consulta]
    else:
        modo_interativo(opcoes)
        return 0

    # Com várias consultas, cada grafo vai para um arquivo numerado
    varias = len(consultas) > 1
    sucesso = [mostrar(sql, opcoes, i if varias else None)
               for i, sql in enumerate(consultas, start=1)]
    return 0 if all(sucesso) or opcoes.exemplos else 1


def _indentar(texto):
    return '\n'.join('    ' + linha for linha in texto.splitlines())


if __name__ == '__main__':
    sys.exit(main())
