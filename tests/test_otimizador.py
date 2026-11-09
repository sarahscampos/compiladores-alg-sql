# -*- coding: utf-8 -*-
"""Testes do otimizador.

Além de conferir o formato da árvore, os testes de equivalência executam a
árvore canônica e a otimizada sobre dados e comparam os resultados. O texto
da expressão não prova nada sobre o significado; o resultado, sim.
"""
import operator
import random
import unittest

from main import caminho_otimizado
from sql_ar import traduzir
from sql_ar.algebra import (Juncao, ProdutoCartesiano, Projecao, Relacao,
                            Renomeacao, Selecao, Semijuncao)
from sql_ar.ast_sql import Coluna, Comparacao, E, Nao, Numero, Ou, Texto

OPERADORES = {'=': operator.eq, '!=': operator.ne, '<>': operator.ne,
              '<': operator.lt, '>': operator.gt, '<=': operator.le, '>=': operator.ge}


# --- Avaliador mínimo de Álgebra Relacional (semântica de conjuntos) --------

def valor_coluna(coluna, linha):
    if coluna.tabela is not None:
        return linha[(coluna.tabela, coluna.nome)]
    # Coluna sem tabela: precisa existir exatamente uma com esse nome. Se o
    # otimizador a tivesse descartado cedo demais, o teste falharia aqui.
    encontradas = [v for (_, nome), v in linha.items() if nome == coluna.nome]
    assert len(encontradas) == 1, f'coluna {coluna} ambígua ou ausente'
    return encontradas[0]


def valor(operando, linha):
    if isinstance(operando, Coluna):
        return valor_coluna(operando, linha)
    if isinstance(operando, Numero):
        return float(operando.lexema)
    assert isinstance(operando, Texto)
    return operando.valor


def verdadeira(condicao, linha):
    if isinstance(condicao, Comparacao):
        return OPERADORES[condicao.operador](valor(condicao.esquerda, linha),
                                             valor(condicao.direita, linha))
    if isinstance(condicao, E):
        return verdadeira(condicao.esquerda, linha) and verdadeira(condicao.direita, linha)
    if isinstance(condicao, Ou):
        return verdadeira(condicao.esquerda, linha) or verdadeira(condicao.direita, linha)
    assert isinstance(condicao, Nao)
    return not verdadeira(condicao.operando, linha)


def sem_repeticao(linhas):
    return [dict(t) for t in {frozenset(linha.items()) for linha in linhas}]


def avaliar(expressao, banco):
    if isinstance(expressao, Relacao):
        return [{(expressao.nome, c): v for c, v in linha.items()}
                for linha in banco[expressao.nome]]
    if isinstance(expressao, Renomeacao):
        return [{(expressao.novo_nome, c): v for (_, c), v in linha.items()}
                for linha in avaliar(expressao.expressao, banco)]
    if isinstance(expressao, Selecao):
        return [l for l in avaliar(expressao.expressao, banco)
                if verdadeira(expressao.condicao, l)]
    if isinstance(expressao, Projecao):
        return sem_repeticao(
            {(a.tabela, a.nome): valor_coluna(a, l) for a in expressao.atributos}
            for l in avaliar(expressao.expressao, banco))
    if isinstance(expressao, Semijuncao):
        direita = avaliar(expressao.direita, banco)
        return [e for e in avaliar(expressao.esquerda, banco)
                if any(verdadeira(expressao.condicao, {**e, **d}) for d in direita)]
    pares = [{**e, **d} for e in avaliar(expressao.esquerda, banco)
             for d in avaliar(expressao.direita, banco)]
    if isinstance(expressao, Juncao):
        return [l for l in pares if verdadeira(expressao.condicao, l)]
    assert isinstance(expressao, ProdutoCartesiano)
    return pares


def conjunto(linhas):
    return {frozenset(linha.items()) for linha in linhas}


def banco_aleatorio(semente):
    gerador = random.Random(semente)

    def tabela(colunas, tamanho):
        return [{c: float(gerador.randint(1, 4)) for c in colunas}
                for _ in range(gerador.randint(0, tamanho))]

    return {
        'a': tabela(['id', 'x', 'k'], 5),
        'b': tabela(['id', 'a_id', 'y'], 5),
        'c': tabela(['id', 'b_id', 'z'], 4),
    }


CONSULTAS_EQUIVALENCIA = [
    # WHERE com produto cartesiano
    'SELECT a.x FROM a, b WHERE a.id = b.a_id',
    'SELECT a.x, b.y FROM a, b WHERE a.id = b.a_id AND a.x > 1 AND b.y < 4',
    'SELECT a.x, c.z FROM a, b, c WHERE a.id = b.a_id AND b.id = c.b_id AND a.k = 2 AND c.z >= 2',
    'SELECT a.x FROM a, b, c WHERE a.id = c.id AND b.id = c.b_id',
    # Tabela sem nenhuma coluna usada: continua influenciando o resultado
    'SELECT a.x FROM a, b',
    'SELECT a.x FROM a, b, c WHERE b.y = 1',
    # OR e NOT não podem ser separados
    'SELECT a.x FROM a, b WHERE a.id = b.a_id AND (a.x = 1 OR b.y = 2)',
    'SELECT a.x FROM a, b WHERE a.x = 1 OR b.y = 2',
    'SELECT a.x FROM a, b WHERE NOT (a.x = 1 AND b.y = 2) AND a.k > 1',
    'SELECT a.x FROM a, b WHERE (a.x = 1 OR a.k = 2) AND b.y != 3',
    # JOIN ... ON, inclusive com condição de um só lado
    'SELECT a.x FROM a JOIN b ON a.id = b.a_id',
    'SELECT b.y FROM a JOIN b ON a.id = b.a_id AND a.x > 1 AND b.y < 3',
    'SELECT a.x FROM a JOIN b ON a.x = 1',
    'SELECT c.z FROM a JOIN b ON a.id = b.a_id JOIN c ON b.id = c.b_id WHERE a.x > 1 AND a.k = c.z',
    'SELECT a.x, c.z FROM a JOIN b ON a.id = b.a_id, c WHERE b.y = c.z',
    'SELECT a.x FROM c, a JOIN b ON a.id = b.a_id WHERE c.z > 1',
    # Apelidos e autojunção
    'SELECT p.x FROM a p, a q WHERE p.id = q.k AND q.x > 1',
    'SELECT p.x, q.x FROM a p JOIN a q ON p.id = q.id WHERE p.k = 1',
    # Colunas sem tabela não podem descer
    'SELECT x FROM a, b WHERE a.id = b.a_id',
    'SELECT x, y FROM a, b WHERE x = 1 AND a.id = b.a_id AND b.y > 1',
    'SELECT a.x FROM a, b WHERE y = 1',
    'SELECT a.x FROM a JOIN b ON x = y',
    # SELECT *
    'SELECT * FROM a, b WHERE a.id = b.a_id AND a.x > 1',
    'SELECT * FROM a JOIN b ON a.id = b.a_id WHERE b.y = 2',
    # Condição só com constantes
    'SELECT a.x FROM a, b WHERE 1 = 1 AND a.id = b.a_id',
    # Uma tabela
    'SELECT x FROM a WHERE x > 1 AND k = 2',
]


class TestesEquivalencia(unittest.TestCase):

    def test_mesmo_resultado_nas_duas_arvores(self):
        nao_vazios = 0
        for consulta in CONSULTAS_EQUIVALENCIA:
            r = traduzir(consulta)
            for semente in range(40):
                banco = banco_aleatorio(semente)
                with self.subTest(consulta=consulta, semente=semente):
                    canonica = conjunto(avaliar(r.expressao, banco))
                    otimizada = conjunto(avaliar(r.expressao_otimizada, banco))
                    self.assertEqual(canonica, otimizada)
                    nao_vazios += bool(canonica)
        # Garante que os dados de fato exercitam as consultas
        self.assertGreater(nao_vazios, len(CONSULTAS_EQUIVALENCIA) * 10)


class TestesFormato(unittest.TestCase):

    def otimizada(self, sql):
        return traduzir(sql).texto_otimizado

    def test_consulta_da_imagem(self):
        self.assertEqual(
            self.otimizada(
                "SELECT Empregado.Sobrenome FROM Projeto, Trabalha, Empregado "
                "WHERE Projeto.NomeProj = 'Aquarius' AND Projeto.ProjNum = Trabalha.ProjNum "
                "AND Trabalha.NumEmp = Empregado.NumEmp AND Empregado.DataNasc = '10/12/90'"),
            "π_{Empregado.Sobrenome}("
            "π_{Trabalha.NumEmp}("
            "π_{Projeto.ProjNum}(σ_{Projeto.NomeProj = 'Aquarius'}(Projeto))"
            " ⋈_{Projeto.ProjNum = Trabalha.ProjNum} "
            "π_{Trabalha.NumEmp, Trabalha.ProjNum}(Trabalha))"
            " ⋈_{Trabalha.NumEmp = Empregado.NumEmp} "
            "π_{Empregado.Sobrenome, Empregado.NumEmp}"
            "(σ_{Empregado.DataNasc = '10/12/90'}(Empregado)))")

    def test_uma_tabela_nao_muda(self):
        r = traduzir('SELECT x FROM a WHERE x > 1 AND k = 2')
        self.assertEqual(r.expressao_otimizada, r.expressao)

    def test_produto_vira_juncao(self):
        self.assertEqual(self.otimizada('SELECT * FROM a, b WHERE a.id = b.a_id'),
                         'a ⋈_{a.id = b.a_id} b')

    def test_produto_sem_condicao_continua_produto(self):
        self.assertEqual(self.otimizada('SELECT * FROM a, b'), 'a × b')

    def test_condicoes_da_mesma_tabela_ficam_juntas(self):
        self.assertEqual(self.otimizada('SELECT * FROM a, b WHERE a.x = 1 AND a.k = 2'),
                         'σ_{a.x = 1 ∧ a.k = 2}(a) × b')

    def test_or_entre_tabelas_nao_e_separado(self):
        self.assertEqual(self.otimizada('SELECT * FROM a, b WHERE a.x = 1 OR b.y = 2'),
                         'a ⋈_{a.x = 1 ∨ b.y = 2} b')

    def test_on_de_um_lado_so_desce(self):
        self.assertEqual(self.otimizada('SELECT * FROM a JOIN b ON a.id = b.a_id AND a.x = 1'),
                         'σ_{a.x = 1}(a) ⋈_{a.id = b.a_id} b')

    def test_selecao_fica_acima_do_renomeado(self):
        self.assertEqual(self.otimizada('SELECT * FROM a p, b WHERE p.x = 1'),
                         'σ_{p.x = 1}(ρ_{p}(a)) × b')

    def test_coluna_sem_tabela_nao_desce(self):
        self.assertEqual(self.otimizada('SELECT * FROM a, b WHERE x = 1 AND a.k = 2'),
                         'σ_{x = 1}(σ_{a.k = 2}(a) × b)')

    def test_coluna_sem_tabela_impede_projecoes_intermediarias(self):
        self.assertEqual(self.otimizada('SELECT x FROM a, b WHERE a.id = b.a_id'),
                         'π_{x}(a ⋈_{a.id = b.a_id} b)')

    def test_nao_gera_projecao_redundante_no_topo(self):
        self.assertEqual(self.otimizada('SELECT a.id, b.a_id FROM a, b WHERE a.id = b.a_id'),
                         'π_{a.id, b.a_id}(π_{a.id}(a) ⋈_{a.id = b.a_id} π_{b.a_id}(b))')

    def test_tabela_sem_coluna_usada_fica_sem_projecao(self):
        self.assertEqual(self.otimizada('SELECT a.x FROM a, b'), 'π_{a.x}(π_{a.x}(a) × b)')

    def test_caminho_do_grafo_otimizado(self):
        self.assertEqual(caminho_otimizado('saida/arvore.svg'), 'saida/arvore_otimizada.svg')


if __name__ == '__main__':
    unittest.main()
