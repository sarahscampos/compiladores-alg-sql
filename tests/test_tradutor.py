# -*- coding: utf-8 -*-
"""Testes do tradutor SQL -> Álgebra Relacional.

Executar a partir da raiz do projeto:  python -m unittest -v
"""
import unittest

from sql_ar import (ErroLexico, ErroSemantico, ErroSintatico, listar_tokens,
                    traduzir)
from sql_ar.ast_sql import Coluna, E, Ou


def ar(sql):
    return traduzir(sql).texto


class TestesObrigatorios(unittest.TestCase):
    """Os oito casos pedidos no enunciado."""

    def test_1_uma_coluna(self):
        self.assertEqual(ar('SELECT nome FROM alunos;'), 'π_{nome}(alunos)')

    def test_2_multiplas_colunas(self):
        self.assertEqual(ar('SELECT nome, idade, curso FROM alunos;'),
                         'π_{nome, idade, curso}(alunos)')

    def test_3_where_uma_condicao(self):
        self.assertEqual(ar('SELECT nome, idade\nFROM alunos\nWHERE idade >= 18;'),
                         'π_{nome, idade}(σ_{idade >= 18}(alunos))')

    def test_4_and(self):
        self.assertEqual(
            ar("SELECT nome FROM alunos WHERE idade >= 18 AND curso = 'Computação';"),
            "π_{nome}(σ_{idade >= 18 ∧ curso = 'Computação'}(alunos))")

    def test_5_or_com_parenteses(self):
        self.assertEqual(
            ar("SELECT nome FROM alunos "
               "WHERE (curso = 'Computação' OR curso = 'Física') AND idade < 30;"),
            "π_{nome}(σ_{(curso = 'Computação' ∨ curso = 'Física') ∧ idade < 30}(alunos))")

    def test_6_produto_cartesiano_com_condicao_de_juncao(self):
        self.assertEqual(
            ar('SELECT alunos.nome, matriculas.disciplina FROM alunos, matriculas '
               'WHERE alunos.id = matriculas.aluno_id;'),
            'π_{alunos.nome, matriculas.disciplina}'
            '(σ_{alunos.id = matriculas.aluno_id}(alunos × matriculas))')

    def test_7_join_on(self):
        self.assertEqual(
            ar('SELECT alunos.nome, matriculas.nota FROM alunos '
               'JOIN matriculas ON alunos.id = matriculas.aluno_id;'),
            'π_{alunos.nome, matriculas.nota}'
            '(alunos ⋈_{alunos.id = matriculas.aluno_id} matriculas)')

    def test_8_consulta_invalida(self):
        with self.assertRaises(ErroSintatico) as ctx:
            traduzir('SELECT nome idade FROM alunos;')
        erro = ctx.exception
        self.assertEqual((erro.linha, erro.coluna), (1, 13))
        self.assertIn("'idade'", erro.mensagem)
        self.assertIn("esperado: ',', '.', FROM", erro.mensagem)


class TestesPrecedencia(unittest.TestCase):

    def test_and_precede_or_na_ast(self):
        # a OR b AND c  deve ser  a OR (b AND c)
        where = traduzir('SELECT x FROM t WHERE a = 1 OR b = 2 AND c = 3').consulta.where
        self.assertIsInstance(where, Ou)
        self.assertIsInstance(where.direita, E)

    def test_parenteses_mudam_o_agrupamento(self):
        where = traduzir('SELECT x FROM t WHERE (a = 1 OR b = 2) AND c = 3').consulta.where
        self.assertIsInstance(where, E)
        self.assertIsInstance(where.esquerda, Ou)

    def test_sem_parenteses_desnecessarios(self):
        self.assertEqual(ar('SELECT x FROM t WHERE a = 1 OR b = 2 AND c = 3'),
                         'π_{x}(σ_{a = 1 ∨ b = 2 ∧ c = 3}(t))')

    def test_associatividade_a_esquerda(self):
        where = traduzir('SELECT x FROM t WHERE a = 1 OR b = 2 OR c = 3').consulta.where
        self.assertIsInstance(where.esquerda, Ou)   # (a OR b) OR c
        self.assertEqual(ar('SELECT x FROM t WHERE a = 1 OR b = 2 OR c = 3'),
                         'π_{x}(σ_{a = 1 ∨ b = 2 ∨ c = 3}(t))')

    def test_parenteses_a_direita_preservados(self):
        self.assertEqual(ar('SELECT x FROM t WHERE a = 1 OR (b = 2 OR c = 3)'),
                         'π_{x}(σ_{a = 1 ∨ (b = 2 ∨ c = 3)}(t))')

    def test_not(self):
        self.assertEqual(ar('SELECT x FROM t WHERE NOT (a = 1 OR b = 2) AND c = 3'),
                         'π_{x}(σ_{¬(a = 1 ∨ b = 2) ∧ c = 3}(t))')


class TestesRecursividade(unittest.TestCase):

    def test_ordem_das_colunas_preservada(self):
        consulta = traduzir('SELECT a, b, c, d, e FROM t').consulta
        self.assertEqual([c.nome for c in consulta.colunas], ['a', 'b', 'c', 'd', 'e'])

    def test_reducoes_da_lista_de_colunas(self):
        reducoes = traduzir('SELECT nome, idade, curso FROM alunos;').reducoes
        lista = [d for e, d in reducoes if e == 'lista_colunas']
        # 1 caso-base + 2 casos recursivos
        self.assertEqual(lista, [
            [('N', 'coluna')],
            [('N', 'lista_colunas'), ('T', ','), ('N', 'coluna')],
            [('N', 'lista_colunas'), ('T', ','), ('N', 'coluna')],
        ])

    def test_derivacao_termina_na_sentenca(self):
        derivacao = traduzir('SELECT nome, idade, curso FROM alunos;').derivacao()
        primeira, ultima = derivacao.splitlines()[0], derivacao.splitlines()[-2]
        self.assertEqual(primeira.strip(), 'consulta')
        self.assertEqual(ultima.strip(), '⇒  SELECT nome , idade , curso FROM alunos ;')

    def test_tres_tabelas_produto(self):
        self.assertEqual(ar('SELECT * FROM a, b, c'), 'a × b × c')

    def test_joins_encadeados(self):
        self.assertEqual(
            ar('SELECT x FROM a JOIN b ON a.i = b.i JOIN c ON b.j = c.j'),
            'π_{x}((a ⋈_{a.i = b.i} b) ⋈_{b.j = c.j} c)')


class TestesLexicos(unittest.TestCase):

    def test_palavras_chave_case_insensitive(self):
        self.assertEqual(ar('sElEcT nome FrOm alunos wHeRe idade >= 18 aNd x = 1'),
                         'π_{nome}(σ_{idade >= 18 ∧ x = 1}(alunos))')

    def test_operadores_relacionais(self):
        tipos = [t for t, _, _ in listar_tokens('= != <> < > <= >=')]
        self.assertEqual(tipos, ['EQ', 'NE', 'NE', 'LT', 'GT', 'LE', 'GE'])

    def test_texto_com_aspas_escapadas(self):
        self.assertEqual(ar("SELECT x FROM t WHERE n = 'it''s'"),
                         "π_{x}(σ_{n = 'it''s'}(t))")

    def test_numero_decimal(self):
        self.assertEqual(ar('SELECT x FROM t WHERE nota >= 7.5'),
                         'π_{x}(σ_{nota >= 7.5}(t))')

    def test_comentario_ignorado(self):
        self.assertEqual(ar('SELECT x -- colunas\nFROM t'), 'π_{x}(t)')

    def test_caractere_invalido(self):
        with self.assertRaises(ErroLexico) as ctx:
            traduzir('SELECT nome FROM alunos WHERE idade > 1 # x')
        self.assertEqual((ctx.exception.linha, ctx.exception.coluna), (1, 41))

    def test_texto_nao_fechado(self):
        with self.assertRaises(ErroLexico) as ctx:
            traduzir("SELECT x FROM t WHERE n = 'abc")
        self.assertIn('não foi fechado', ctx.exception.mensagem)


class TestesSintaticos(unittest.TestCase):

    def test_consulta_vazia(self):
        with self.assertRaises(ErroSintatico) as ctx:
            traduzir('')
        self.assertIn('esperado: SELECT', ctx.exception.mensagem)

    def test_virgula_sobrando(self):
        with self.assertRaises(ErroSintatico):
            traduzir('SELECT nome, FROM t')

    def test_condicao_incompleta_em_outra_linha(self):
        with self.assertRaises(ErroSintatico) as ctx:
            traduzir('SELECT nome\nFROM alunos\nWHERE idade >= 18 AND ;')
        self.assertEqual((ctx.exception.linha, ctx.exception.coluna), (3, 23))

    def test_parentese_nao_fechado(self):
        with self.assertRaises(ErroSintatico) as ctx:
            traduzir('SELECT x FROM t WHERE (a = 1')
        self.assertIn('fim inesperado', ctx.exception.mensagem)


class TestesSemanticos(unittest.TestCase):

    def test_apelido_gera_renomeacao(self):
        self.assertEqual(
            ar('SELECT a1.nome FROM alunos a1, alunos AS a2 WHERE a1.id != a2.id'),
            'π_{a1.nome}(σ_{a1.id != a2.id}(ρ_{a1}(alunos) × ρ_{a2}(alunos)))')

    def test_tabela_repetida_sem_apelido(self):
        with self.assertRaises(ErroSemantico):
            traduzir('SELECT x FROM alunos, alunos')

    def test_qualificador_desconhecido(self):
        with self.assertRaises(ErroSemantico):
            traduzir('SELECT p.nome FROM alunos')

    def test_nome_original_apos_apelido(self):
        with self.assertRaises(ErroSemantico) as ctx:
            traduzir('SELECT alunos.nome FROM alunos a')
        self.assertIn("use 'a.nome'", ctx.exception.mensagem)

    def test_on_so_ve_tabelas_do_join(self):
        with self.assertRaises(ErroSemantico):
            traduzir('SELECT x FROM a, b JOIN c ON a.k = c.k')

    def test_coluna_qualificada_na_ast(self):
        coluna = traduzir('SELECT alunos.nome FROM alunos').consulta.colunas[0]
        self.assertEqual(coluna, Coluna('nome', tabela='alunos'))


if __name__ == '__main__':
    unittest.main()
