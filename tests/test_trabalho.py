# -*- coding: utf-8 -*-
"""Testes dos itens pedidos no enunciado do Trabalho P2: tabela de produções
e ações semânticas (4c), árvore de derivação e árvore anotada (4d) e a
marcação das modificações em relação ao calc.py (6).
"""
import contextlib
import io
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

from main import caminho_anotado, main
from sql_ar import traduzir
from sql_ar.derivacao import formatar_valor
from sql_ar.grafo import construir_grafo_derivacao, gerar_svg_derivacao, percorrer
from sql_ar.parser import SqlParser, tabela_producoes

SVG = '{http://www.w3.org/2000/svg}'
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestesTabelaProducoes(unittest.TestCase):

    def test_todas_as_producoes_tem_regra(self):
        tabela = tabela_producoes()
        self.assertEqual(len(tabela), len(SqlParser._grammar.Productions) - 1)
        for numero, producao, regra in tabela:
            self.assertTrue(regra, f'produção {numero} ({producao}) sem regra semântica')

    def test_regra_da_lista_recursiva(self):
        regras = {producao: regra for _, producao, regra in tabela_producoes()}
        self.assertEqual(regras['lista_colunas → lista_colunas COMMA coluna'],
                         'lista_colunas.val = lista_colunas₁.val + [coluna.val]')
        self.assertEqual(regras['clausula_where → ε'], 'clausula_where.val = nulo')

    def test_opcao_producoes(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = main(['--producoes'])
        self.assertEqual(codigo, 0)
        self.assertIn('lista_colunas → lista_colunas COMMA coluna', saida.getvalue())
        self.assertIn('subconsulta.val = Subconsulta(selecao.val)', saida.getvalue())


class TestesArvoreAnotada(unittest.TestCase):

    def test_lista_mostra_cada_passo_da_recursao(self):
        arvore = traduzir('SELECT nome, idade, curso FROM alunos;').arvore_sintatica(anotada=True)
        self.assertIn('lista_colunas.val = [nome]', arvore)
        self.assertIn('lista_colunas.val = [nome, idade]', arvore)
        self.assertIn('lista_colunas.val = [nome, idade, curso]', arvore)

    def test_condicao_e_precedencia(self):
        arvore = traduzir('SELECT x FROM t WHERE a = 1 OR b = 2 AND c = 3').arvore_sintatica(
            anotada=True)
        self.assertIn('condicao.val = a = 1 OR b = 2 AND c = 3', arvore)
        self.assertIn('conjuncao.val = b = 2 AND c = 3', arvore)
        self.assertIn('op_rel.val = "="', arvore)

    def test_raiz_tem_a_consulta(self):
        arvore = traduzir('SELECT * FROM t').arvore_sintatica(anotada=True)
        self.assertTrue(arvore.startswith(
            'consulta.val = Consulta(colunas=*, origem=[t], where=nulo)'))

    def test_sem_anotacao_continua_igual(self):
        arvore = traduzir('SELECT x FROM t').arvore_sintatica()
        self.assertNotIn('.val', arvore)
        self.assertTrue(arvore.startswith('consulta\n'))

    def test_formatar_valor(self):
        r = traduzir("SELECT a.x FROM t a JOIN u ON a.i = u.i "
                     "WHERE NOT (a.x = 1 OR a.y = 'z') AND a.k IN (SELECT w FROM v)")
        self.assertEqual(
            formatar_valor(r.consulta.where),
            "NOT (a.x = 1 OR a.y = 'z') AND a.k IN (SELECT ...)")
        self.assertEqual(formatar_valor(r.consulta.origem), '[t AS a JOIN u ON a.i = u.i]')

    def test_tabela_derivada_na_arvore_anotada(self):
        arvore = traduzir('SELECT t.x FROM (SELECT x FROM a) t').arvore_sintatica(anotada=True)
        self.assertIn('tabela.val = (SELECT ...) AS t', arvore)
        self.assertIn('origem=[(SELECT ...) AS t]', arvore)
        self.assertNotIn('TabelaDerivada(', arvore)


class TestesGrafoDerivacao(unittest.TestCase):

    def test_nos_e_arestas(self):
        arvore = traduzir('SELECT nome FROM alunos;').arvore_derivacao()
        svg = ET.fromstring(gerar_svg_derivacao(arvore))
        nos = svg.findall(f'{SVG}g')
        # o ε da clausula_where vazia também vira um nó
        self.assertIn('vazio', [g.get('class') for g in nos])
        self.assertEqual(len(svg.findall(f'{SVG}line')), len(nos) - 1)

    def test_anotada_tem_os_valores(self):
        arvore = traduzir('SELECT nome, idade FROM alunos;').arvore_derivacao()
        textos = ' '.join(ET.fromstring(gerar_svg_derivacao(arvore, anotada=True)).itertext())
        self.assertIn('val = [nome, idade]', textos)
        self.assertNotIn('val = [nome, idade]',
                         ' '.join(ET.fromstring(gerar_svg_derivacao(arvore)).itertext()))

    def test_sem_sobreposicao(self):
        arvore = traduzir("SELECT a, b FROM t WHERE (x = 1 OR y = 'texto longo aqui') "
                          "AND z IN (SELECT w FROM u)").arvore_derivacao()
        nos = list(percorrer(construir_grafo_derivacao(arvore, anotada=True)))
        for i, a in enumerate(nos):
            for b in nos[i + 1:]:
                sobrepoe_x = abs(a.x - b.x) < (a.largura + b.largura) / 2
                sobrepoe_y = a.y < b.y + b.altura and b.y < a.y + a.altura
                self.assertFalse(sobrepoe_x and sobrepoe_y, (a.linhas, b.linhas))

    def test_opcao_salva_dois_arquivos(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, 'derivacao.svg')
            with contextlib.redirect_stdout(io.StringIO()):
                main(['SELECT nome FROM alunos;', '--grafo-derivacao', caminho])
            for arquivo in (caminho, caminho_anotado(caminho)):
                self.assertEqual(ET.parse(arquivo).getroot().tag, f'{SVG}svg')


class TestesMarcacao(unittest.TestCase):

    def test_arquivos_marcados(self):
        """Item 6: cada arquivo do tradutor indica se é novo ou modificado."""
        pasta = os.path.join(RAIZ, 'sql_ar')
        for nome in sorted(os.listdir(pasta)):
            if nome.endswith('.py'):
                with open(os.path.join(pasta, nome), encoding='utf-8') as arquivo:
                    inicio = arquivo.read(600)
                with self.subTest(arquivo=nome):
                    self.assertTrue('[NOVO]' in inicio or '[MODIFICADO]' in inicio)


if __name__ == '__main__':
    unittest.main()
