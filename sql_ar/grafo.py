# -*- coding: utf-8 -*-
# [NOVO] Arquivo criado neste trabalho; não existe no exemplo calc.py.
"""Desenha árvores como grafos em SVG: a árvore de consulta (Álgebra
Relacional) e a árvore de derivação, simples ou anotada com os atributos.

Usa apenas a biblioteca padrão: o resultado é um arquivo .svg que abre em
qualquer navegador. Na árvore de consulta a raiz fica no topo (último
operador avaliado) e as relações ficam nas folhas, como nos livros de banco
de dados.
"""
import textwrap
from dataclasses import dataclass, field
from html import escape

from .algebra import decompor, formatar
from .derivacao import formatar_valor, rotulo_anotado

# Medidas em pixels. A fonte é monoespaçada para que a largura de um texto
# possa ser estimada sem medir a fonte (não há como medir sem um navegador).
LARGURA_CARACTERE = 8.6
ALTURA_LINHA = 18
LARGURA_SIMBOLO = 30
MARGEM_INTERNA = 12
ALTURA_MINIMA = 44
ESPACO_HORIZONTAL = 28
ESPACO_VERTICAL = 42
MARGEM = 20
# Textos maiores que isto quebram em várias linhas dentro do nó
MAX_CARACTERES_LINHA = 30

CLASSE_POR_SIMBOLO = {
    '': 'relacao', 'π': 'projecao', 'σ': 'selecao', '⋈': 'juncao',
    '×': 'produto', 'ρ': 'renomeacao', '⋉': 'semijuncao',
}

ESTILO = """
    .aresta { stroke: #64748b; stroke-width: 1.5; }
    .no { stroke-width: 1.5; }
    text { font-family: Consolas, 'DejaVu Sans Mono', Menlo, monospace; fill: #1e293b; }
    .simbolo { font-size: 22px; font-weight: bold; }
    .detalhe { font-size: 14px; }
    .relacao .no { fill: #f1f5f9; stroke: #475569; }
    .relacao .detalhe { font-weight: bold; }
    .projecao .no { fill: #dbeafe; stroke: #2563eb; }
    .selecao .no { fill: #fef3c7; stroke: #d97706; }
    .juncao .no { fill: #dcfce7; stroke: #16a34a; }
    .produto .no { fill: #fee2e2; stroke: #dc2626; }
    .renomeacao .no { fill: #f3e8ff; stroke: #9333ea; }
    .semijuncao .no { fill: #ccfbf1; stroke: #0d9488; }
    .nao-terminal .no { fill: #eef2ff; stroke: #4f46e5; }
    .nao-terminal text.detalhe:first-of-type { font-weight: bold; }
    .terminal .no { fill: #ecfdf5; stroke: #059669; }
    .vazio .no { fill: #ffffff; stroke: #94a3b8; stroke-dasharray: 4 3; }
"""


@dataclass
class NoGrafo:
    simbolo: str
    linhas: list
    filhos: list = field(default_factory=list)
    classe: str = ''
    largura: float = 0
    altura: float = 0
    largura_subarvore: float = 0
    # Centro horizontal e topo do nó, definidos pelo layout
    x: float = 0
    y: float = 0


def construir_grafo(expressao):
    """Converte a expressão relacional em nós já medidos e posicionados."""
    return _posicionar_arvore(_construir_no(expressao))


def construir_grafo_derivacao(arvore, anotada=False):
    """Mesmo layout para a árvore de derivação (derivacao.No)."""
    return _posicionar_arvore(_construir_no_derivacao(arvore, anotada))


def _posicionar_arvore(raiz):
    alturas = []
    _medir_niveis(raiz, 0, alturas)
    topos = [MARGEM]
    for altura in alturas:
        topos.append(topos[-1] + altura + ESPACO_VERTICAL)
    _posicionar(raiz, MARGEM, 0, topos, alturas)
    return raiz


def percorrer(raiz):
    """Todos os nós do grafo, em pré-ordem."""
    yield raiz
    for filho in raiz.filhos:
        yield from percorrer(filho)


def gerar_svg(expressao):
    return _desenhar(construir_grafo(expressao), formatar(expressao))


def salvar_svg(expressao, caminho):
    with open(caminho, 'w', encoding='utf-8') as arquivo:
        arquivo.write(gerar_svg(expressao))


def gerar_svg_derivacao(arvore, anotada=False):
    titulo = 'Árvore de derivação anotada' if anotada else 'Árvore de derivação'
    return _desenhar(construir_grafo_derivacao(arvore, anotada), titulo)


def salvar_svg_derivacao(arvore, caminho, anotada=False):
    with open(caminho, 'w', encoding='utf-8') as arquivo:
        arquivo.write(gerar_svg_derivacao(arvore, anotada))


def _desenhar(raiz, titulo):
    nos = list(percorrer(raiz))
    largura = raiz.largura_subarvore + 2 * MARGEM
    altura = max(no.y + no.altura for no in nos) + MARGEM

    partes = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{largura:.0f}" '
        f'height="{altura:.0f}" viewBox="0 0 {largura:.0f} {altura:.0f}">',
        f'<title>{escape(titulo)}</title>',
        f'<style>{ESTILO}</style>',
        f'<rect width="{largura:.0f}" height="{altura:.0f}" fill="#ffffff"/>',
    ]
    # As arestas vêm antes para ficarem atrás dos nós
    for no in nos:
        for filho in no.filhos:
            partes.append(
                f'<line class="aresta" x1="{no.x:.1f}" y1="{no.y + no.altura:.1f}" '
                f'x2="{filho.x:.1f}" y2="{filho.y:.1f}"/>')
    partes.extend(_svg_no(no) for no in nos)
    partes.append('</svg>')
    return '\n'.join(partes) + '\n'


def _construir_no(expressao):
    simbolo, detalhe, filhos = decompor(expressao)
    no = NoGrafo(simbolo, _quebrar(detalhe), [_construir_no(filho) for filho in filhos],
                 CLASSE_POR_SIMBOLO[simbolo])
    return _medir(no)


def _construir_no_derivacao(no, anotada):
    if no.terminal:
        return _medir(NoGrafo('', [f'"{no.rotulo}"'], [], 'terminal'))
    linhas = [no.rotulo]
    if anotada and rotulo_anotado(no):
        linhas += _quebrar('val = ' + formatar_valor(no.valor))
    # Produção vazia: a folha ε deixa explícito que nada foi derivado
    filhos = ([_construir_no_derivacao(f, anotada) for f in no.filhos]
              or [_medir(NoGrafo('', ['ε'], [], 'vazio'))])
    return _medir(NoGrafo('', linhas, filhos, 'nao-terminal'))


def _quebrar(texto):
    return textwrap.wrap(texto, MAX_CARACTERES_LINHA, break_on_hyphens=False)


def _medir(no):
    simbolo, linhas = no.simbolo, no.linhas
    largura_texto = max(map(len, linhas), default=0) * LARGURA_CARACTERE
    largura_simbolo = LARGURA_SIMBOLO if simbolo else 0
    no.largura = largura_texto + largura_simbolo + 2 * MARGEM_INTERNA
    no.altura = max(ALTURA_MINIMA, len(linhas) * ALTURA_LINHA + 2 * MARGEM_INTERNA)

    # Cada subárvore reserva uma faixa horizontal só dela; por isso nós de
    # subárvores diferentes nunca se sobrepõem.
    soma_filhos = (sum(f.largura_subarvore for f in no.filhos)
                   + ESPACO_HORIZONTAL * max(len(no.filhos) - 1, 0))
    no.largura_subarvore = max(no.largura, soma_filhos)
    return no


def _medir_niveis(no, nivel, alturas):
    if nivel == len(alturas):
        alturas.append(0)
    alturas[nivel] = max(alturas[nivel], no.altura)
    for filho in no.filhos:
        _medir_niveis(filho, nivel + 1, alturas)


def _posicionar(no, esquerda, nivel, topos, alturas):
    no.x = esquerda + no.largura_subarvore / 2
    # Centraliza o nó na altura do seu nível
    no.y = topos[nivel] + (alturas[nivel] - no.altura) / 2
    soma_filhos = (sum(f.largura_subarvore for f in no.filhos)
                   + ESPACO_HORIZONTAL * max(len(no.filhos) - 1, 0))
    cursor = no.x - soma_filhos / 2
    for filho in no.filhos:
        _posicionar(filho, cursor, nivel + 1, topos, alturas)
        cursor += filho.largura_subarvore + ESPACO_HORIZONTAL


def _svg_no(no):
    esquerda = no.x - no.largura / 2
    centro_y = no.y + no.altura / 2
    partes = [
        f'<g class="{no.classe}">',
        f'<rect class="no" x="{esquerda:.1f}" y="{no.y:.1f}" width="{no.largura:.1f}" '
        f'height="{no.altura:.1f}" rx="8"/>',
    ]
    x_texto = esquerda + MARGEM_INTERNA
    if no.simbolo:
        # Sem detalhe (produto cartesiano), o símbolo fica centralizado no nó
        x_simbolo, ancora = (x_texto, 'start') if no.linhas else (no.x, 'middle')
        partes.append(f'<text class="simbolo" x="{x_simbolo:.1f}" y="{centro_y:.1f}" '
                      f'text-anchor="{ancora}" dominant-baseline="central">{no.simbolo}</text>')
        x_texto += LARGURA_SIMBOLO
    primeira_linha = centro_y - (len(no.linhas) - 1) * ALTURA_LINHA / 2
    for i, linha in enumerate(no.linhas):
        partes.append(f'<text class="detalhe" x="{x_texto:.1f}" '
                      f'y="{primeira_linha + i * ALTURA_LINHA:.1f}" '
                      f'dominant-baseline="central" xml:space="preserve">{escape(linha)}</text>')
    partes.append('</g>')
    return ''.join(partes)
