# -*- coding: utf-8 -*-
"""Testes das subconsultas (comparação e IN, não correlacionadas).

Os testes de equivalência executam a mesma consulta no SQLite (biblioteca
padrão do Python) e comparam o resultado com o das árvores de Álgebra
Relacional, canônica e otimizada. Assim a tradução é checada contra um banco
de dados real, e não só contra o texto esperado.
"""
import random
import sqlite3
import unittest
import xml.etree.ElementTree as ET

from sql_ar import ErroSemantico, ErroSintatico, traduzir
from sql_ar.algebra import Projecao, Semijuncao
from sql_ar.ast_sql import Em, Subconsulta
from sql_ar.grafo import gerar_svg
from sql_ar.parser import SqlParser
from tests.test_otimizador import avaliar, valor_coluna


def ar(sql):
    return traduzir(sql).texto


class TestesTraducao(unittest.TestCase):

    def test_consulta_da_issue(self):
        self.assertEqual(
            ar('SELECT nome FROM alunos WHERE idade > ( SELECT idade FROM alunos WHERE id = 1 );'),
            'π_{nome}(alunos ⋉_{alunos.idade > sub1.idade} '
            'ρ_{sub1}(π_{idade}(σ_{id = 1}(alunos))))')

    def test_in(self):
        self.assertEqual(
            ar('SELECT nome FROM alunos WHERE id IN '
               '(SELECT aluno_id FROM matriculas WHERE nota > 7)'),
            'π_{nome}(alunos ⋉_{alunos.id = sub1.aluno_id} '
            'ρ_{sub1}(π_{aluno_id}(σ_{nota > 7}(matriculas))))')

    def test_demais_condicoes_ficam_na_selecao(self):
        self.assertEqual(
            ar("SELECT nome FROM alunos WHERE curso = 'Física' "
               "AND id IN (SELECT aluno_id FROM matriculas) AND idade > 18"),
            "π_{nome}(σ_{curso = 'Física' ∧ idade > 18}"
            "(alunos ⋉_{alunos.id = sub1.aluno_id} ρ_{sub1}(π_{aluno_id}(matriculas))))")

    def test_subconsulta_a_esquerda_mantem_a_ordem(self):
        self.assertEqual(ar('SELECT x FROM a WHERE (SELECT y FROM b) < x'),
                         'π_{x}(a ⋉_{sub1.y < a.x} ρ_{sub1}(π_{y}(b)))')

    def test_subconsultas_aninhadas(self):
        self.assertEqual(
            ar('SELECT x FROM a WHERE x IN (SELECT y FROM b WHERE y IN (SELECT z FROM c))'),
            'π_{x}(a ⋉_{a.x = sub1.y} ρ_{sub1}(π_{y}(b ⋉_{b.y = sub2.z} ρ_{sub2}(π_{z}(c)))))')

    def test_apelido_nao_colide_com_tabela(self):
        self.assertEqual(ar('SELECT * FROM sub1 WHERE x IN (SELECT y FROM b)'),
                         'sub1 ⋉_{sub1.x = sub2.y} ρ_{sub2}(π_{y}(b))')

    def test_varias_tabelas_coluna_nao_e_qualificada(self):
        self.assertEqual(
            ar('SELECT a.x FROM a, b WHERE a.id = b.a_id AND y < (SELECT z FROM c)'),
            'π_{a.x}(σ_{a.id = b.a_id}((a × b) ⋉_{y < sub1.z} ρ_{sub1}(π_{z}(c))))')

    def test_ast(self):
        where = SqlParser().analisar('SELECT x FROM a WHERE x IN (SELECT y FROM b)').where
        self.assertIsInstance(where, Em)
        self.assertIsInstance(where.subconsulta, Subconsulta)

    def test_derivacao_mostra_a_autoincorporacao(self):
        derivacao = traduzir('SELECT x FROM a WHERE x IN (SELECT y FROM b)').derivacao()
        self.assertIn('[subconsulta → ( selecao )]', derivacao)
        self.assertIn('[comparacao → operando IN subconsulta]', derivacao)

    def test_gramatica_sem_conflitos(self):
        tabela = SqlParser._lrtable
        self.assertEqual((tabela.sr_conflicts, tabela.rr_conflicts), ([], []))

    def test_grafo_com_semijuncao(self):
        svg = ET.fromstring(gerar_svg(
            traduzir('SELECT nome FROM alunos WHERE idade > (SELECT idade FROM alunos)').expressao))
        classes = [g.get('class') for g in svg.findall('{http://www.w3.org/2000/svg}g')]
        self.assertEqual(classes, ['projecao', 'semijuncao', 'relacao',
                                   'renomeacao', 'projecao', 'relacao'])


class TestesOtimizacao(unittest.TestCase):

    def otimizada(self, sql):
        return traduzir(sql).texto_otimizado

    def test_selecao_desce_abaixo_da_semijuncao(self):
        self.assertEqual(self.otimizada('SELECT * FROM a WHERE x > 1 AND x IN (SELECT y FROM b)'),
                         'σ_{x > 1}(a) ⋉_{a.x = sub1.y} ρ_{sub1}(π_{y}(b))')

    def test_subconsulta_e_otimizada_separadamente(self):
        self.assertEqual(
            self.otimizada('SELECT a.x FROM a WHERE a.id IN '
                           '(SELECT b.a_id FROM b, c WHERE b.id = c.b_id AND c.z > 1)'),
            'π_{a.x}(π_{a.x, a.id}(a) ⋉_{a.id = sub1.a_id} '
            'ρ_{sub1}(π_{b.a_id}(π_{b.a_id, b.id}(b) ⋈_{b.id = c.b_id} π_{c.b_id}(σ_{c.z > 1}(c)))))')

    def test_projecao_mantem_coluna_da_semijuncao(self):
        self.assertEqual(
            self.otimizada('SELECT a.x FROM a, b WHERE a.id = b.a_id AND a.k IN (SELECT c.z FROM c)'),
            'π_{a.x}(π_{a.x, a.k}(π_{a.x, a.k, a.id}(a) ⋈_{a.id = b.a_id} π_{b.a_id}(b)) '
            '⋉_{a.k = sub1.z} ρ_{sub1}(π_{c.z}(c)))')


class TestesErros(unittest.TestCase):

    def erro(self, sql, tipo=ErroSemantico):
        with self.assertRaises(tipo) as ctx:
            traduzir(sql)
        return ctx.exception.mensagem

    def test_correlacionada(self):
        self.assertIn('correlacionadas',
                      self.erro('SELECT x FROM alunos a WHERE x IN (SELECT y FROM b WHERE b.k = a.k)'))

    def test_not_in(self):
        self.assertIn('NOT IN', self.erro('SELECT x FROM a WHERE x NOT IN (SELECT y FROM b)'))

    def test_not_antes_do_in(self):
        self.assertIn('OR ou NOT', self.erro('SELECT x FROM a WHERE NOT x IN (SELECT y FROM b)'))

    def test_exists(self):
        self.assertIn('EXISTS', self.erro('SELECT x FROM a WHERE EXISTS (SELECT y FROM b)'))

    def test_dentro_de_or(self):
        self.assertIn('OR ou NOT',
                      self.erro('SELECT x FROM a WHERE x = 1 OR x IN (SELECT y FROM b)'))

    def test_no_on(self):
        self.assertIn('ON', self.erro('SELECT x FROM a JOIN b ON a.i IN (SELECT y FROM c)'))

    def test_select_estrela_na_subconsulta(self):
        self.assertIn('uma coluna', self.erro('SELECT x FROM a WHERE x IN (SELECT * FROM b)'))

    def test_duas_colunas_na_subconsulta(self):
        self.assertIn('uma coluna', self.erro('SELECT x FROM a WHERE x IN (SELECT y, z FROM b)'))

    def test_duas_subconsultas(self):
        self.assertIn('duas subconsultas',
                      self.erro('SELECT x FROM a WHERE (SELECT y FROM b) = (SELECT z FROM c)'))

    def test_nome_ambiguo(self):
        self.assertIn('ambíguo', self.erro('SELECT x FROM a, b WHERE z = (SELECT z FROM c)'))

    def test_tabela_inexistente_na_subconsulta(self):
        self.assertIn("'q'", self.erro('SELECT x FROM a WHERE x IN (SELECT q.y FROM b)'))

    def test_ponto_e_virgula_dentro_da_subconsulta(self):
        self.erro('SELECT x FROM a WHERE x IN (SELECT y FROM b;)', ErroSintatico)

    def test_parentese_nao_fechado(self):
        self.erro('SELECT x FROM a WHERE x IN (SELECT y FROM b', ErroSintatico)


# --- Comparação com o SQLite ------------------------------------------------

CONSULTAS_SQLITE = [
    # Comparação com subconsulta escalar (a.id é único, então ela devolve
    # no máximo uma linha, como o SQL exige)
    'SELECT x FROM a WHERE k > (SELECT x FROM a WHERE id = 2)',
    'SELECT x FROM a WHERE x = (SELECT k FROM a WHERE id = 1)',
    'SELECT a.x FROM a WHERE a.k <= (SELECT x FROM a WHERE id = 3)',
    'SELECT x FROM a WHERE (SELECT x FROM a WHERE id = 3) < k',
    'SELECT x FROM a WHERE 2 < (SELECT x FROM a WHERE id = 1)',
    'SELECT x FROM a WHERE k <> (SELECT x FROM a WHERE id = 99)',     # subconsulta vazia
    # IN
    'SELECT x FROM a WHERE id IN (SELECT a_id FROM b WHERE y > 2)',
    'SELECT * FROM a WHERE id IN (SELECT a_id FROM b)',
    'SELECT b.y FROM a, b WHERE a.id = b.a_id AND a.k IN (SELECT z FROM c)',
    'SELECT y FROM a, b WHERE a.id = b.a_id AND y IN (SELECT z FROM c WHERE z > 1)',
    'SELECT a.x, b.y FROM a JOIN b ON a.id = b.a_id WHERE b.y IN (SELECT z FROM c)',
    'SELECT x FROM a WHERE id IN (SELECT b.a_id FROM b, c WHERE b.id = c.b_id AND c.z > 1)',
    # Aninhadas e combinadas
    'SELECT x FROM a WHERE id IN (SELECT a_id FROM b WHERE y IN (SELECT z FROM c WHERE z > 1))',
    'SELECT x FROM a WHERE k >= (SELECT k FROM a WHERE id = 1) AND id IN (SELECT a_id FROM b)',
    'SELECT x FROM a WHERE x > 1 AND id IN (SELECT a_id FROM b) AND k < 4',
    # Consultas sem subconsulta também são conferidas
    'SELECT a.x, b.y FROM a, b WHERE a.id = b.a_id AND (a.x > 1 OR b.y < 2)',
    'SELECT x FROM a WHERE NOT (x = 1 OR k = 2)',
    'SELECT p.x FROM a p, a q WHERE p.id = q.k AND q.x > 1',
]


def criar_banco(semente):
    gerador = random.Random(semente)
    valor = lambda: float(gerador.randint(1, 4))   # noqa: E731
    ids_a = gerador.sample(range(1, 7), gerador.randint(0, 6))
    return {
        'a': [{'id': float(i), 'x': valor(), 'k': valor()} for i in ids_a],
        'b': [{'id': valor(), 'a_id': float(gerador.randint(1, 6)), 'y': valor()}
              for _ in range(gerador.randint(0, 6))],
        'c': [{'id': valor(), 'b_id': valor(), 'z': valor()}
              for _ in range(gerador.randint(0, 5))],
    }


def executar_sqlite(sql, banco):
    conexao = sqlite3.connect(':memory:')
    try:
        for tabela, linhas in banco.items():
            colunas = {'a': ['id', 'x', 'k'], 'b': ['id', 'a_id', 'y'],
                       'c': ['id', 'b_id', 'z']}[tabela]
            conexao.execute(f'CREATE TABLE {tabela} ({", ".join(c + " REAL" for c in colunas)})')
            conexao.executemany(
                f'INSERT INTO {tabela} VALUES ({", ".join("?" for _ in colunas)})',
                [tuple(linha[c] for c in colunas) for linha in linhas])
        return set(conexao.execute(sql).fetchall())
    finally:
        conexao.close()


def executar_algebra(expressao, banco):
    linhas = avaliar(expressao, banco)
    if isinstance(expressao, Projecao):
        return {tuple(valor_coluna(a, linha) for a in expressao.atributos) for linha in linhas}
    # SELECT *: a ordem das colunas segue as tabelas, como no SQLite
    return {tuple(linha.values()) for linha in linhas}


class TestesSqlite(unittest.TestCase):

    def test_mesmo_resultado_que_o_sqlite(self):
        nao_vazios = 0
        for sql in CONSULTAS_SQLITE:
            resultado = traduzir(sql)
            for semente in range(30):
                banco = criar_banco(semente)
                with self.subTest(sql=sql, semente=semente):
                    esperado = executar_sqlite(sql, banco)
                    self.assertEqual(executar_algebra(resultado.expressao, banco), esperado)
                    self.assertEqual(executar_algebra(resultado.expressao_otimizada, banco),
                                     esperado)
                    nao_vazios += bool(esperado)
        # Garante que os dados de fato exercitam as consultas
        self.assertGreater(nao_vazios, len(CONSULTAS_SQLITE) * 8)

    def test_traducao_usa_semijuncao(self):
        expressao = traduzir(CONSULTAS_SQLITE[0]).expressao
        self.assertIsInstance(expressao.expressao, Semijuncao)


if __name__ == '__main__':
    unittest.main()
