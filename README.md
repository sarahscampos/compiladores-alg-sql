# Tradutor SQL → Álgebra Relacional com SLY

Este projeto traduz consultas `SELECT … FROM … WHERE …` (com `JOIN … ON`) para
expressões da Álgebra Relacional. O **lexer** e o **parser** são feitos com a
biblioteca [SLY](https://github.com/dabeaz/sly) (`sly.Lexer` / `sly.Parser`,
LALR(1)). A consulta inteira é analisada pela gramática; o código não usa
expressões regulares nem manipulação de texto para fazer a análise sintática.

```
SELECT nome, idade FROM alunos WHERE idade >= 18;
        ⟶   π_{nome, idade}(σ_{idade >= 18}(alunos))
```

Sumário:

1. [Fundamentos da gramática e da autoincorporação](#1-fundamentos-da-gramática-e-da-autoincorporação)
2. [Gramática formal completa](#2-gramática-formal-completa)
3. [Precedência e ações semânticas](#3-precedência-e-ações-semânticas)
4. [Código Python](#4-código-python)
5. [Instalação e execução](#5-instalação-e-execução)
6. [Exemplos, derivações e testes](#6-exemplos-derivações-e-testes)
7. [Limitações e melhorias possíveis](#7-limitações-e-melhorias-possíveis)
8. [Trabalho P2: atendimento ao enunciado](#8-trabalho-p2-atendimento-ao-enunciado)

> **Para a avaliação do Trabalho P2**, a seção 8 relaciona cada item do enunciado
> com o lugar onde ele é atendido. Ela inclui a tabela completa de produções e
> ações semânticas, as árvores de derivação (simples e anotada), as modificações
> em relação ao exemplo `calc.py` e o prompt utilizado.

---

## 1. Fundamentos da gramática e da autoincorporação

### 1.1 As três fases de análise

| Fase | Arquivo | Entrada → Saída | O que verifica |
|---|---|---|---|
| Léxica | [sql_ar/lexer.py](sql_ar/lexer.py) | texto → sequência de *tokens* | se cada trecho do texto forma um token válido (palavra-chave, identificador, número, texto, operador) |
| Sintática | [sql_ar/parser.py](sql_ar/parser.py) | tokens → AST ([sql_ar/ast_sql.py](sql_ar/ast_sql.py)) | se a sequência de tokens pertence à linguagem gerada pela gramática |
| Semântica | [sql_ar/semantica.py](sql_ar/semantica.py) | AST → AST validada | se os nomes usados fazem sentido: tabelas repetidas, qualificadores (`x.col`) inexistentes, uso do nome original depois de um apelido, tabelas visíveis no `ON` |
| Tradução | [sql_ar/algebra.py](sql_ar/algebra.py) | AST → árvore relacional → texto | — |

A análise léxica é feita com expressões regulares, como é próprio dessa fase:
cada token é definido por um padrão. A estrutura da consulta (listas, aninhamento,
precedência) é tratada só pela gramática livre de contexto, porque linguagens com
parênteses aninhados **não são regulares**.

### 1.2 Recursão gramatical e autoincorporação

Um não terminal `A` é **recursivo** quando `A ⇒⁺ α A β`. Há três casos:

| Forma | Nome | Exemplo nesta gramática |
|---|---|---|
| `A ⇒⁺ A β` | recursão à esquerda | `lista_colunas → lista_colunas , coluna` |
| `A ⇒⁺ α A` | recursão à direita | `fator → NOT fator` |
| `A ⇒⁺ α A β`, com α ≠ ε e β ≠ ε | **autoincorporação** (*self-embedding*) em sentido estrito | `condicao ⇒⁺ ( condicao )` e `selecao ⇒⁺ … ( selecao )` (subconsulta no `WHERE` ou no `FROM`) |

> **Observação sobre o termo.** Em muitos materiais didáticos, "autoincorporação"
> é usado para qualquer regra em que o não terminal aparece no próprio lado
> direito, e é nesse sentido que o enunciado o aplica a `lista_colunas`.
> Na teoria de linguagens formais (Chomsky), *self-embedding* exige símbolos dos
> dois lados (α e β não vazios). Isso importa porque uma gramática **sem**
> autoincorporação estrita gera apenas linguagens regulares. Listas separadas por
> vírgula são regulares (`coluna (, coluna)*`). Parênteses balanceados não são.
> Nesta gramática, a autoincorporação estrita aparece em dois lugares:
> `condicao → conjuncao → fator → ( condicao )` e nas subconsultas, em que uma
> consulta inteira aparece dentro de outra:
> `selecao ⇒⁺ SELECT … WHERE operando op_rel ( selecao )` e
> `selecao ⇒⁺ SELECT … FROM ( selecao ) t` (seção 6.7).
> As duas formas de recursão estão no código e são explicadas abaixo.

### 1.3 A lista de colunas recursiva à esquerda

```
lista_colunas → lista_colunas , coluna      (caso recursivo)
              | coluna                      (caso-base)
```

* **Caso-base** (`lista_colunas → coluna`): uma lista com uma única coluna.
  É ele que encerra a recursão. Sem essa regra, `lista_colunas` não derivaria
  nenhuma sentença.
* **Caso recursivo** (`lista_colunas → lista_colunas , coluna`): uma lista é uma
  lista menor seguida de `,` e mais uma coluna. O não terminal aparece na
  **primeira** posição do lado direito, por isso a recursão é **à esquerda**.
* **Tamanho variável**: aplicando o caso recursivo *n − 1* vezes e o caso-base
  uma vez, obtemos `coluna , coluna , … , coluna` com *n* colunas, para
  qualquer *n ≥ 1*. A linguagem gerada é `coluna (, coluna)*`.

**Por que preservar a recursão à esquerda no SLY?** O SLY gera um parser
**LR** (ascendente). A recursão à esquerda é a forma natural para parsers LR:

* a pilha não cresce com o tamanho da lista, porque cada `, coluna` é reduzido
  assim que lido;
* a lista é montada **da esquerda para a direita**, na ordem do texto. A ação
  semântica só faz `append`.

(Num parser descendente recursivo LL, a recursão à esquerda causaria laço
infinito e precisaria ser eliminada. Aqui ela não é um problema.)

Derivação mais à direita de `nome , idade , curso`:

```
lista_colunas
⇒ lista_colunas , coluna                       (recursivo)
⇒ lista_colunas , curso
⇒ lista_colunas , coluna , curso               (recursivo)
⇒ lista_colunas , idade , curso
⇒ coluna , idade , curso                       (caso-base)
⇒ nome , idade , curso
```

Árvore resultante, inclinada para a esquerda:

```
            lista_colunas
           /      |      \
   lista_colunas  ,     coluna(curso)
    /    |    \
lista_col ,  coluna(idade)
   |
coluna(nome)
```

O parser LR executa essa derivação **ao contrário** (reduções):
`nome` → `coluna` → `lista_colunas` (caso-base, lista = `[nome]`), depois
`lista_colunas , idade` → `lista_colunas` (lista = `[nome, idade]`), depois
`lista_colunas , curso` → `lista_colunas` (lista = `[nome, idade, curso]`).

As produções recursivas aparecem no código SLY marcadas com `[RECURSIVA]`:

```python
# [RECURSIVA à esquerda] caso recursivo
@_('lista_colunas COMMA coluna')
def lista_colunas(self, p):
    self._registrar(p)
    p.lista_colunas.append(p.coluna)
    return p.lista_colunas

# Caso-base: uma única coluna inicia a lista
@_('coluna')
def lista_colunas(self, p):
    self._registrar(p)
    return [p.coluna]
```

Outras produções recursivas: `lista_tabelas` (mesma estrutura),
`item_from` (`JOIN` encadeado), `condicao` (`OR`), `conjuncao` (`AND`),
`fator → NOT fator` (à direita) e `fator → ( condicao )` (autoincorporação).

---

## 2. Gramática formal completa

**Símbolo inicial:** `consulta`

**Terminais** (tokens do lexer):

| Token | Lexema |
|---|---|
| `SELECT FROM WHERE AND OR NOT JOIN INNER ON AS IN EXISTS` | palavras-chave, sem diferença entre maiúsculas e minúsculas |
| `ID` | `[A-Za-z_][A-Za-z0-9_]*` (exceto palavras-chave) |
| `NUMBER` | `\d+(\.\d+)?` |
| `STRING` | `'…'` (aspas internas escritas como `''`) |
| `COMMA DOT STAR SEMI LPAREN RPAREN` | `,` `.` `*` `;` `(` `)` |
| `EQ NE LT GT LE GE` | `=` `!=`/`<>` `<` `>` `<=` `>=` |

Ignorados pelo lexer: espaços, tabulações, quebras de linha (contadas para as
mensagens de erro) e comentários `-- …`.

**Não terminais:** `consulta, selecao, fim, clausula_where, lista_selecao, lista_colunas,
coluna, referencia, lista_tabelas, item_from, tabela, condicao, conjuncao, fator,
comparacao, op_rel, operando, subconsulta`

**Produções (BNF):**

```bnf
consulta       → selecao fim

selecao        → SELECT lista_selecao FROM lista_tabelas clausula_where

fim            → SEMI
               | ε

clausula_where → WHERE condicao
               | ε

lista_selecao  → STAR
               | lista_colunas

lista_colunas  → lista_colunas COMMA coluna        (* recursiva à esquerda *)
               | coluna

coluna         → referencia

referencia     → ID
               | ID DOT ID                         (* identificador qualificado *)

lista_tabelas  → lista_tabelas COMMA item_from     (* recursiva à esquerda *)
               | item_from

item_from      → item_from JOIN tabela ON condicao         (* recursiva à esquerda *)
               | item_from INNER JOIN tabela ON condicao
               | tabela

tabela         → ID
               | ID ID                             (* apelido *)
               | ID AS ID
               | subconsulta ID                    (* tabela derivada *)
               | subconsulta AS ID
               | subconsulta                       (* reconhecido, mas rejeitado na semântica *)

condicao       → condicao OR conjuncao             (* nível 1: OR *)
               | conjuncao

conjuncao      → conjuncao AND fator               (* nível 2: AND *)
               | fator

fator          → NOT fator                         (* nível 3: NOT, recursiva à direita *)
               | LPAREN condicao RPAREN            (* autoincorporação *)
               | EXISTS subconsulta                (* reconhecido, mas rejeitado na semântica *)
               | comparacao

comparacao     → operando op_rel operando
               | operando IN subconsulta
               | operando NOT IN subconsulta       (* reconhecido, mas rejeitado na semântica *)

op_rel         → EQ | NE | LT | GT | LE | GE

operando       → referencia | NUMBER | STRING
               | subconsulta

subconsulta    → LPAREN selecao RPAREN             (* autoincorporação *)
```

`selecao` existe separada de `consulta` porque a subconsulta não pode ter `;`.
Após um `(`, o parser decide pelo token seguinte se está agrupando uma condição
ou abrindo uma subconsulta: `SELECT` só pode iniciar uma `selecao`.

A mesma gramática em EBNF, só como referência (o SLY recebe a forma BNF acima):

```ebnf
consulta   = selecao [ ";" ] ;
selecao    = "SELECT" ( "*" | coluna { "," coluna } ) "FROM" item_from { "," item_from }
             [ "WHERE" condicao ] ;
item_from  = tabela { [ "INNER" ] "JOIN" tabela "ON" condicao } ;
tabela     = ID [ [ "AS" ] ID ] | subconsulta [ [ "AS" ] ID ] ;
condicao   = conjuncao { "OR" conjuncao } ;
conjuncao  = fator { "AND" fator } ;
fator      = "NOT" fator | "(" condicao ")" | "EXISTS" subconsulta
           | operando op_rel operando | operando [ "NOT" ] "IN" subconsulta ;
operando   = referencia | NUMBER | STRING | subconsulta ;
subconsulta = "(" selecao ")" ;
referencia = ID [ "." ID ] ;
```

O SLY gera para essa gramática uma tabela LALR(1) com **77 estados e nenhum
conflito** (shift/reduce = 0, reduce/reduce = 0), o que foi verificado por
`SqlParser._lrtable.sr_conflicts` / `rr_conflicts`. Logo, a gramática não é
ambígua para o SLY.

---

## 3. Precedência e ações semânticas

### 3.1 Precedência codificada na gramática

Em vez da tabela `precedence` do SLY (usada em [calc.py](calc.py)), a
precedência lógica é **estratificada em níveis**. Cada nível só pode conter
o nível seguinte:

```
condicao  (OR)   →  conjuncao (AND)  →  fator (NOT, parênteses, comparação)
```

Consequências:

* **AND precede OR.** Um `OR` só aparece em `condicao`. Para que ele fique
  dentro de um `AND`, é preciso voltar a `condicao` por
  `fator → ( condicao )`, ou seja, usando parênteses explícitos.
* **Associatividade à esquerda.** As regras `condicao → condicao OR conjuncao`
  e `conjuncao → conjuncao AND fator` são recursivas à esquerda, então
  `a OR b OR c` vira `(a OR b) OR c`.
* **Sem ambiguidade.** Cada sentença tem uma única árvore. O SLY confirma
  isso: não há conflitos.

Escolhi essa forma por ser a mais didática: a precedência fica visível nas
produções e nas árvores de derivação. Com a tabela `precedence` o resultado
seria o mesmo, mas a gramática seria ambígua e o desempate ficaria escondido
no gerador do parser.

Exemplo: `a = 1 OR b = 2 AND c = 3` (árvore real impressa por `--arvore`,
resumida):

```
condicao
├── condicao ── conjuncao ── fator ── comparacao (a = 1)
├── "OR"
└── conjuncao
    ├── conjuncao ── fator ── comparacao (b = 2)
    ├── "AND"
    └── fator ── comparacao (c = 3)
```

O `AND` fica **mais fundo** na árvore, então é agrupado primeiro:
`a = 1 ∨ (b = 2 ∧ c = 3)`. Com `(a = 1 OR b = 2) AND c = 3`, a raiz passa a
ser `conjuncao` e o `OR` fica dentro de `fator → ( condicao )`.

### 3.2 Ações semânticas e estruturas intermediárias

Cada produção tem uma ação Python que devolve um nó da **AST** (dataclasses
imutáveis em [sql_ar/ast_sql.py](sql_ar/ast_sql.py)). Nenhuma ação monta
strings de Álgebra Relacional.

| Produção | Ação semântica (valor sintetizado) |
|---|---|
| `referencia → ID DOT ID` | `Coluna(nome=ID₁, tabela=ID₀)` |
| `lista_colunas → coluna` | `[coluna]` |
| `lista_colunas → lista_colunas , coluna` | `lista.append(coluna)` |
| `lista_selecao → *` | `None` (sem projeção) |
| `tabela → ID AS ID` | `Tabela(nome, apelido)` |
| `item_from → item_from JOIN tabela ON condicao` | `Join(esq, dir, condicao)` |
| `condicao → condicao OR conjuncao` | `Ou(esq, dir)` |
| `conjuncao → conjuncao AND fator` | `E(esq, dir)` |
| `fator → NOT fator` | `Nao(fator)` |
| `fator → ( condicao )` | `condicao` (o agrupamento já está na árvore) |
| `comparacao → operando op_rel operando` | `Comparacao(esq, op, dir)` |
| `comparacao → operando IN subconsulta` | `Em(operando, subconsulta)` |
| `subconsulta → ( selecao )` | `Subconsulta(consulta)` |
| `tabela → subconsulta ID` | `TabelaDerivada(consulta, apelido)` |
| `selecao → SELECT …` | `Consulta(colunas, origem, where)` |
| `consulta → selecao fim` | a própria `Consulta` |

São atributos **sintetizados**: cada valor vem dos filhos, como numa
gramática S-atribuída, que é o modelo natural de um parser ascendente.
A tabela acima mostra só as produções principais. A tabela completa, com as 46
produções, está na seção 8.5 e é impressa por `python main.py --producoes`.

Toda ação chama também `self._registrar(p)`. Esse método usa
`self.production` (definido pelo SLY antes de cada redução) para anotar a
produção aplicada. A partir dessas anotações, [sql_ar/derivacao.py](sql_ar/derivacao.py)
reconstrói a **derivação mais à direita** (as reduções em ordem inversa) e a
**árvore sintática**.

### 3.3 Tradução para a Álgebra Relacional

[sql_ar/algebra.py](sql_ar/algebra.py) converte a AST numa árvore de operadores
(`Relacao`, `Renomeacao`, `Selecao`, `Projecao`, `ProdutoCartesiano`,
`Juncao`, `Semijuncao`) seguindo a forma canônica:

```
SELECT L FROM R₁, …, Rₙ WHERE C   ⟶   π_{L}( σ_{C}( R₁ × … × Rₙ ) )
```

| SQL | Álgebra Relacional |
|---|---|
| `FROM R₁, R₂, R₃` | `R₁ × R₂ × R₃`, que equivale a `(R₁ × R₂) × R₃` |
| `R JOIN S ON c` | `R ⋈_{c} S` (junção theta) |
| `alunos a` / `alunos AS a` | `ρ_{a}(alunos)` |
| `WHERE C` | `σ_{C}(…)` |
| `SELECT L` | `π_{L}(…)` |
| `SELECT *` | sem `π` |
| `AND` / `OR` / `NOT` | `∧` / `∨` / `¬` |
| `WHERE x op (SELECT y …)` / `WHERE x IN (SELECT y …)` | `R ⋉_{x op sub1.y} ρ_{sub1}(…)` (semijunção, seção 6.7) |
| `FROM (SELECT …) t` | `ρ_{t}(…)`, a tradução da subconsulta renomeada (seção 6.7) |

A formatação usa parênteses **mínimos que preservam a estrutura**: um `∨`
dentro de um `∧` recebe parênteses. Um operador do mesmo nível à direita,
que só existe se o usuário escreveu parênteses (ex.: `a OR (b OR c)`),
também os mantém. Na álgebra, `×` é associativo e é escrito sem parênteses.
Junções encadeadas são parentizadas: `(a ⋈ b) ⋈ c`.

Por padrão, a tradução **não** transforma `σ_{R.a = S.b}(R × S)` em `R ⋈ S`: a
saída reflete a consulta como foi escrita. A opção `--otimizar` mostra também a
versão otimizada (seção 6.6).

---

## 4. Código Python

O código está completo e é executável. Fica no pacote `sql_ar/`:

| Arquivo | Conteúdo |
|---|---|
| [sql_ar/lexer.py](sql_ar/lexer.py) | `SqlLexer(sly.Lexer)`: tokens, palavras-chave case-insensitive, strings, números, comentários, contagem de linhas e `error()` para caracteres inválidos e strings não fechadas |
| [sql_ar/parser.py](sql_ar/parser.py) | `SqlParser(sly.Parser)`: todas as produções da seção 2 com ações semânticas e `error()` que lista os tokens esperados |
| [sql_ar/ast_sql.py](sql_ar/ast_sql.py) | nós da AST SQL |
| [sql_ar/semantica.py](sql_ar/semantica.py) | análise semântica (escopo de tabelas e apelidos, onde as subconsultas podem aparecer) |
| [sql_ar/algebra.py](sql_ar/algebra.py) | nós da Álgebra Relacional, tradução e formatação (linear e em árvore) |
| [sql_ar/otimizador.py](sql_ar/otimizador.py) | otimização algébrica: seleções e projeções descem na árvore |
| [sql_ar/grafo.py](sql_ar/grafo.py) | árvore de consulta como grafo em SVG, só com a biblioteca padrão |
| [sql_ar/derivacao.py](sql_ar/derivacao.py) | derivação mais à direita e árvore de derivação (simples e anotada) a partir das reduções |
| [sql_ar/erros.py](sql_ar/erros.py) | `ErroLexico`, `ErroSintatico`, `ErroSemantico` com linha, coluna e destaque `^` |
| [sql_ar/tradutor.py](sql_ar/tradutor.py) | `traduzir(sql)`: encadeia as fases |
| [main.py](main.py) | interface de linha de comando e modo interativo |
| [tests/test_tradutor.py](tests/test_tradutor.py) | testes `unittest` do tradutor e do grafo |
| [tests/test_otimizador.py](tests/test_otimizador.py) | testes do otimizador, incluindo a equivalência entre as árvores |
| [tests/test_subconsultas.py](tests/test_subconsultas.py) | testes das subconsultas, incluindo a comparação com o SQLite |
| [tests/test_trabalho.py](tests/test_trabalho.py) | testes dos itens do enunciado: tabela de produções, árvores anotadas e marcação do código |

Uso como biblioteca:

```python
from sql_ar import traduzir, ErroTraducao

try:
    r = traduzir("SELECT nome FROM alunos WHERE idade >= 18;")
    print(r.texto)              # π_{nome}(σ_{idade >= 18}(alunos))
    print(r.arvore_algebra())   # árvore de operadores
    print(r.derivacao())        # derivação mais à direita
except ErroTraducao as e:
    print(e.destacar(sql))
```

### Pontos de compatibilidade com a API real do SLY 0.5 (revisados)

* `tokens = { … }` com nomes não definidos e `@_(…)` dentro da classe são
  resolvidos pela metaclasse do SLY. Os linters podem acusá-los como nomes
  indefinidos, mas eles funcionam.
* Os padrões de tokens são testados **na ordem de definição**. Por isso `<=`,
  `>=` e `!=|<>` vêm antes de `<`, `>` e `=`.
* Palavras-chave são reconhecidas na função `ID`, que troca `t.type`
  (comparando em maiúsculas). O mecanismo `ID['select'] = SELECT` do SLY
  diferencia maiúsculas de minúsculas e não serviria.
* Produções vazias são escritas como `@_('')`. Várias alternativas cabem num
  mesmo decorador: `@_('EQ', 'NE', …)`.
* Símbolos repetidos são acessados como `p.ID0`/`p.ID1` e `p.operando0`/`p.operando1`.
* `start = 'consulta'` define o símbolo inicial.
* **Armadilha encontrada:** durante `parse()`, o SLY substitui `self.tokens`
  pelo gerador de tokens. Por isso o parser consulta `SqlLexer.tokens`, e não
  `self.tokens`, para saber se um símbolo é terminal.
* `error()` lança exceção, então não há recuperação de erro: a análise para
  no primeiro erro. A lista de tokens esperados usa `_lrtable` e
  `statestack`, que são internos do SLY. O código está protegido: se esses
  atributos mudarem, só a lista some da mensagem.

---

## 5. Instalação e execução

Testado com Python 3.14.7 e 3.15.0 e SLY 0.5, no Windows. Outras versões não foram testadas.

### 5.1 Instalação

Abra o terminal na **pasta do projeto** (a que contém `main.py`). Todos os comandos
desta seção partem dela.

Crie um ambiente virtual (opcional, mas evita misturar dependências):

```bash
python -m venv .venv
```

Ative o ambiente no PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Ou, no Git Bash:

```bash
source .venv/Scripts/activate
```

Instale a dependência:

```bash
python -m pip install -r requirements.txt
```

Se o terminal não reconhecer `python`, use `py` no lugar. Se o PowerShell bloquear a
ativação, rode antes `Set-ExecutionPolicy -Scope Process RemoteSigned`, que vale só
para aquela janela.

Para conferir, rode os testes. A última linha deve ser `OK`:

```bash
python -m unittest
```

### 5.2 Traduzir uma consulta

```bash
python main.py "SELECT nome, idade FROM alunos WHERE idade >= 18;"
```

Saída:

```
SQL: SELECT nome, idade FROM alunos WHERE idade >= 18;
AR:  π_{nome, idade}(σ_{idade >= 18}(alunos))
```

**Coloque a consulta entre aspas duplas.** Sem elas, o terminal divide a consulta em
vários argumentos. Os textos do SQL continuam com aspas simples:

```bash
python main.py "SELECT nome FROM alunos WHERE curso = 'Física';"
```

### 5.3 Opções

As opções podem vir antes ou depois da consulta e podem ser combinadas.
`python main.py --help` mostra esta mesma lista.

| Opção | O que faz |
|---|---|
| `-f ARQUIVO`, `--arquivo ARQUIVO` | lê as consultas de um arquivo (seção 5.5) |
| `--exemplos` | roda as consultas de exemplo. A última é inválida de propósito, para mostrar a mensagem de erro |
| `--tokens` | mostra os tokens reconhecidos pelo lexer |
| `--arvore` | mostra a árvore relacional e a árvore de derivação como texto |
| `--anotada` | mostra a árvore de derivação anotada com o atributo `.val` de cada não terminal |
| `--derivacao` | mostra a derivação mais à direita |
| `--producoes` | mostra a tabela de produções e regras semânticas (funciona sem consulta) |
| `--grafo-derivacao ARQUIVO.svg` | salva a árvore de derivação em `ARQUIVO.svg` e a anotada em `ARQUIVO_anotada.svg` |
| `--otimizar` | mostra também a expressão otimizada (seção 6.6) |
| `--grafo ARQUIVO.svg` | salva a árvore de consulta como grafo |
| `--abrir` | abre os grafos salvos no navegador. Sem `--grafo` nem `--grafo-derivacao`, salva em `arvore_consulta.svg` |

Mostrar a derivação e as árvores:

```bash
python main.py --derivacao --arvore "SELECT nome, idade, curso FROM alunos;"
```

Gerar o grafo e abrir no navegador (seção 6.5):

```bash
python main.py "SELECT nome FROM alunos WHERE idade >= 18;" --grafo arvore.svg --abrir
```

Comparar as árvores canônica e otimizada. Este comando salva dois arquivos,
`arvore.svg` e `arvore_otimizada.svg`:

```bash
python main.py "SELECT a.nome FROM alunos a, matriculas m WHERE a.id = m.aluno_id AND m.nota > 7;" --otimizar --grafo arvore.svg
```

Os grafos são salvos na pasta atual, e um arquivo com o mesmo nome é substituído.
Os arquivos `arvore*.svg` da raiz do projeto são ignorados pelo Git.

### 5.4 Modo interativo

```bash
python main.py
```

A consulta pode ocupar várias linhas e termina com `;` ou com uma linha vazia. Os comandos
começam com `:` e, com exceção de `:exemplos` e `:sair`, ligam ou desligam uma opção,
que continua valendo para as consultas seguintes.

| Comando | O que faz |
|---|---|
| `:tokens`, `:arvore`, `:anotada`, `:derivacao`, `:otimizar` | ligam ou desligam a opção de mesmo nome |
| `:producoes` | mostra a tabela de produções e regras semânticas |
| `:grafo` | liga ou desliga o grafo, salvo sempre em `arvore_consulta.svg` |
| `:exemplos` | roda as consultas de exemplo |
| `:sair` | encerra (`Ctrl+C` também) |

Exemplo de sessão:

```
sql> :otimizar
otimizar: ligado
sql> SELECT a.nome
...> FROM alunos a, matriculas m
...> WHERE a.id = m.aluno_id;

SQL: SELECT a.nome FROM alunos a, matriculas m WHERE a.id = m.aluno_id;
AR:  π_{a.nome}(σ_{a.id = m.aluno_id}(ρ_{a}(alunos) × ρ_{m}(matriculas)))
AR otimizada: π_{a.nome}(π_{a.nome, a.id}(ρ_{a}(alunos)) ⋈_{a.id = m.aluno_id} π_{m.aluno_id}(ρ_{m}(matriculas)))
sql> :sair
```

### 5.5 Consultas em arquivo

```bash
python main.py -f consultas.sql
```

O arquivo deve estar em UTF-8, e cada consulta deve **terminar em `;` no fim de uma linha**:

```sql
SELECT nome
FROM alunos;

SELECT idade FROM alunos WHERE idade > 1;
```

Duas consultas na mesma linha são lidas como uma só e geram erro de sintaxe.
Com `--grafo`, cada consulta gera um arquivo numerado: `arvore_1.svg`, `arvore_2.svg` etc.

### 5.6 Exemplos e testes

Rodar as consultas de exemplo (a última termina em erro de propósito):

```bash
python main.py --exemplos
```

Rodar os testes mostrando cada um. Execute este comando a partir da pasta do projeto:

```bash
python -m unittest -v
```

---

## 6. Exemplos, derivações e testes

As saídas abaixo foram **obtidas executando o programa** (`python main.py
--exemplos`) e os oito casos estão automatizados em
[tests/test_tradutor.py](tests/test_tradutor.py) (classe `TestesObrigatorios`).
Resultado: `Ran 116 tests … OK`.

### 6.1 Testes obrigatórios

**1. Uma coluna**
```
SELECT nome FROM alunos;
π_{nome}(alunos)
```

**2. Múltiplas colunas**
```
SELECT nome, idade, curso FROM alunos;
π_{nome, idade, curso}(alunos)
```

**3. WHERE com uma condição**
```
SELECT nome, idade FROM alunos WHERE idade >= 18;
π_{nome, idade}(σ_{idade >= 18}(alunos))
```

**4. Condições com AND**
```
SELECT nome FROM alunos WHERE idade >= 18 AND curso = 'Computação';
π_{nome}(σ_{idade >= 18 ∧ curso = 'Computação'}(alunos))
```

**5. OR com parênteses**
```
SELECT nome FROM alunos WHERE (curso = 'Computação' OR curso = 'Física') AND idade < 30;
π_{nome}(σ_{(curso = 'Computação' ∨ curso = 'Física') ∧ idade < 30}(alunos))
```
Sem os parênteses, `curso = 'Computação' OR curso = 'Física' AND idade < 30`
seria agrupado como `curso = 'Computação' ∨ (curso = 'Física' ∧ idade < 30)`.

**6. Duas tabelas: produto cartesiano + condição de junção**
```
SELECT alunos.nome, matriculas.disciplina FROM alunos, matriculas
WHERE alunos.id = matriculas.aluno_id;
π_{alunos.nome, matriculas.disciplina}(σ_{alunos.id = matriculas.aluno_id}(alunos × matriculas))
```

**7. JOIN … ON** (com apelidos, gerando ρ)
```
SELECT a.nome, m.nota FROM alunos a JOIN matriculas m ON a.id = m.aluno_id WHERE m.nota > 7;
π_{a.nome, m.nota}(σ_{m.nota > 7}(ρ_{a}(alunos) ⋈_{a.id = m.aluno_id} ρ_{m}(matriculas)))
```
Árvore de operadores (`--arvore`):
```
π a.nome, m.nota
└── σ m.nota > 7
    └── ⋈ a.id = m.aluno_id
        ├── ρ a
        │   └── alunos
        └── ρ m
            └── matriculas
```

**8. Consulta sintaticamente inválida** (vírgula ausente)
```
SELECT nome idade FROM alunos;
Erro sintático (linha 1, coluna 13): token inesperado 'idade' (identificador); esperado: ',', '.', FROM
    SELECT nome idade FROM alunos;
                ^
```

### 6.2 Outros casos verificados

| Entrada | Saída |
|---|---|
| `SELECT * FROM a, b, c` | `a × b × c` |
| `SELECT x FROM a JOIN b ON a.i=b.i JOIN c ON b.j <> c.j, d` | `π_{x}(((a ⋈_{a.i = b.i} b) ⋈_{b.j <> c.j} c) × d)` |
| `SELECT x FROM alunos a1, alunos a2 WHERE a1.id != a2.id` | `π_{x}(σ_{a1.id != a2.id}(ρ_{a1}(alunos) × ρ_{a2}(alunos)))` |
| `select * from a where not (x = 1 or y = 2) or (z = 3 or w = 4)` | `σ_{¬(x = 1 ∨ y = 2) ∨ (z = 3 ∨ w = 4)}(a)` |
| `SELECT nome FROM alunos WHERE idade > 1 # x` | `Erro léxico (linha 1, coluna 41): caractere inválido '#'` |
| `SELECT nome FROM alunos WHERE nome = 'abc` | `Erro léxico (linha 1, coluna 38): texto entre aspas simples não foi fechado` |
| `SELECT nome, FROM t` | `Erro sintático (linha 1, coluna 14): token inesperado 'FROM' (FROM); esperado: identificador` |
| *(consulta vazia)* | `Erro sintático (linha 1, coluna 1): fim inesperado da consulta; esperado: SELECT` |
| `SELECT x FROM alunos, alunos` | `Erro semântico (…): a tabela 'alunos' aparece mais de uma vez no FROM; use apelidos diferentes …` |
| `SELECT alunos.nome FROM alunos a` | `Erro semântico (…): a tabela 'alunos' foi renomeada para 'a'; use 'a.nome'` |
| `SELECT x FROM a, b JOIN c ON a.k = c.k` | `Erro semântico (…): 'a.k' referencia a tabela 'a', que não está disponível neste ponto da consulta (tabelas visíveis: b, c)` |

### 6.3 Derivação passo a passo com três colunas

Saída real de `python main.py --derivacao "SELECT nome, idade, curso FROM alunos;"`.
Em cada passo o **não terminal mais à direita** é expandido, e entre colchetes
aparece a produção aplicada:

```
    consulta
 ⇒  SELECT lista_selecao FROM lista_tabelas clausula_where fim
        [consulta → SELECT lista_selecao FROM lista_tabelas clausula_where fim]
 ⇒  SELECT lista_selecao FROM lista_tabelas clausula_where ;
        [fim → ;]
 ⇒  SELECT lista_selecao FROM lista_tabelas ;
        [clausula_where → ε]
 ⇒  SELECT lista_selecao FROM item_from ;
        [lista_tabelas → item_from]
 ⇒  SELECT lista_selecao FROM tabela ;
        [item_from → tabela]
 ⇒  SELECT lista_selecao FROM alunos ;
        [tabela → alunos]
 ⇒  SELECT lista_colunas FROM alunos ;
        [lista_selecao → lista_colunas]
 ⇒  SELECT lista_colunas , coluna FROM alunos ;
        [lista_colunas → lista_colunas , coluna]        ← recursivo (3ª coluna)
 ⇒  SELECT lista_colunas , referencia FROM alunos ;
        [coluna → referencia]
 ⇒  SELECT lista_colunas , curso FROM alunos ;
        [referencia → curso]
 ⇒  SELECT lista_colunas , coluna , curso FROM alunos ;
        [lista_colunas → lista_colunas , coluna]        ← recursivo (2ª coluna)
 ⇒  SELECT lista_colunas , referencia , curso FROM alunos ;
        [coluna → referencia]
 ⇒  SELECT lista_colunas , idade , curso FROM alunos ;
        [referencia → idade]
 ⇒  SELECT coluna , idade , curso FROM alunos ;
        [lista_colunas → coluna]                        ← caso-base (1ª coluna)
 ⇒  SELECT referencia , idade , curso FROM alunos ;
        [coluna → referencia]
 ⇒  SELECT nome , idade , curso FROM alunos ;
        [referencia → nome]
```

Árvore sintática (`--arvore`), trecho da seleção:

```
lista_selecao
└── lista_colunas                 ← valor: [nome, idade, curso]
    ├── lista_colunas             ← valor: [nome, idade]
    │   ├── lista_colunas         ← valor: [nome]        (caso-base)
    │   │   └── coluna ── referencia ── "nome"
    │   ├── ","
    │   └── coluna ── referencia ── "idade"
    ├── ","
    └── coluna ── referencia ── "curso"
```

**Como a recursividade constrói a projeção.** A derivação expande a lista da
direita para a esquerda, mas o parser LR **reduz na ordem inversa**, da
esquerda para a direita:

1. lê `nome`, reduz `referencia → ID`, `coluna → referencia` e
   `lista_colunas → coluna`, e o valor passa a ser `[Coluna('nome')]`;
2. lê `, idade`, reduz `lista_colunas → lista_colunas , coluna`, e o valor passa
   a ser `[nome, idade]`;
3. lê `, curso`, reduz de novo o caso recursivo, e o valor passa a ser
   `[nome, idade, curso]`;
4. `lista_selecao → lista_colunas` repassa a lista, `consulta` cria
   `Consulta(colunas=(nome, idade, curso), …)`, e a tradução gera
   `Projecao((nome, idade, curso), Relacao('alunos'))`, isto é,
   `π_{nome, idade, curso}(alunos)`.

Cada aplicação do caso recursivo acrescenta **exatamente um atributo** à
projeção, e o caso-base fornece o primeiro. Por isso a gramática aceita
qualquer número de colunas e mantém a ordem.

### 6.4 Preservação da precedência

| Entrada | AST | Saída |
|---|---|---|
| `a = 1 OR b = 2 AND c = 3` | `Ou(a=1, E(b=2, c=3))` | `a = 1 ∨ b = 2 ∧ c = 3` |
| `(a = 1 OR b = 2) AND c = 3` | `E(Ou(a=1, b=2), c=3)` | `(a = 1 ∨ b = 2) ∧ c = 3` |
| `a = 1 OR b = 2 OR c = 3` | `Ou(Ou(a=1, b=2), c=3)` | `a = 1 ∨ b = 2 ∨ c = 3` |
| `a = 1 OR (b = 2 OR c = 3)` | `Ou(a=1, Ou(b=2, c=3))` | `a = 1 ∨ (b = 2 ∨ c = 3)` |
| `NOT (a = 1 OR b = 2) AND c = 3` | `E(Nao(Ou(…)), c=3)` | `¬(a = 1 ∨ b = 2) ∧ c = 3` |

Esses casos são verificados em `TestesPrecedencia`, que inspeciona a AST, e não
só o texto final.

### 6.5 Árvore de consulta como grafo

A opção `--grafo ARQUIVO.svg` desenha a expressão relacional como um grafo: a
raiz é o último operador avaliado e as folhas são as relações. O arquivo abre
em qualquer navegador e não exige instalar o Graphviz. Com várias consultas
(`-f` ou `--exemplos`), cada grafo vai para um arquivo numerado, como `arvore_1.svg`.
No modo interativo, `:grafo` salva cada consulta em `arvore_consulta.svg`.

```bash
python main.py "SELECT Empregado.Sobrenome FROM Projeto, Trabalha, Empregado WHERE Projeto.NomeProj = 'Aquarius' AND Projeto.ProjNum = Trabalha.ProjNum AND Trabalha.NumEmp = Empregado.NumEmp AND Empregado.DataNasc = '10/12/90';" --otimizar --grafo docs/arvore_exemplo.svg
```

![Árvore de consulta canônica](docs/arvore_exemplo.svg)

Esse grafo mostra a tradução canônica: uma seleção só, acima de todos os
produtos. A versão otimizada está na próxima seção.

### 6.6 Otimização da árvore de consulta

A opção `--otimizar` aplica à árvore relacional as heurísticas clássicas
([sql_ar/otimizador.py](sql_ar/otimizador.py)), para descartar linhas e colunas
o mais cedo possível:

1. **Cascata de seleções:** `σ_{c₁ ∧ c₂}(R)` equivale a `σ_{c₁}(σ_{c₂}(R))`, então
   cada conjunção é tratada separadamente.
2. **Seleções descem:** cada condição vai para a subárvore mais baixa que contém
   todas as tabelas citadas. Condições da mesma tabela voltam a formar um único `σ`.
3. **`×` vira `⋈`:** a condição que liga os dois lados de um produto cartesiano
   passa a ser a condição da junção.
4. **Projeções descem:** cada subárvore produz só as colunas usadas acima dela,
   inclusive as necessárias para as junções.

Para a consulta da seção 6.5:

![Árvore de consulta otimizada](docs/arvore_exemplo_otimizada.svg)

```
π_{Empregado.Sobrenome}(
  π_{Trabalha.NumEmp}(
    π_{Projeto.ProjNum}(σ_{Projeto.NomeProj = 'Aquarius'}(Projeto))
      ⋈_{Projeto.ProjNum = Trabalha.ProjNum}
    π_{Trabalha.NumEmp, Trabalha.ProjNum}(Trabalha))
  ⋈_{Trabalha.NumEmp = Empregado.NumEmp}
  π_{Empregado.Sobrenome, Empregado.NumEmp}(σ_{Empregado.DataNasc = '10/12/90'}(Empregado)))
```

**Limites impostos pela falta de esquema.** Sem o esquema do banco, o programa não
sabe de qual tabela vem uma coluna sem qualificador. Por segurança:

| Situação | Comportamento | Exemplo |
|---|---|---|
| Condição com coluna não qualificada | não desce | `SELECT * FROM a, b WHERE x = 1` mantém `σ_{x = 1}(a × b)` |
| Consulta com várias tabelas e alguma coluna não qualificada | sem projeções intermediárias | `SELECT x FROM a, b WHERE a.id = b.a_id` gera `π_{x}(a ⋈_{a.id = b.a_id} b)` |
| `SELECT *` | sem projeções, pois todas as colunas são necessárias | `SELECT * FROM a, b WHERE a.id = b.a_id` gera `a ⋈_{a.id = b.a_id} b` |
| `OR` entre tabelas | não é separado, porque só `∧` permite a cascata | `a.x = 1 OR b.y = 2` fica inteiro na junção |
| Tabela sem nenhuma coluna usada | sem `π`, mas continua na árvore, pois afeta o resultado | `SELECT a.x FROM a, b` gera `π_{a.x}(π_{a.x}(a) × b)` |

Por isso a consulta acima usa `Empregado.Sobrenome`, qualificado. Quando todas as
colunas têm tabela, a árvore sai no formato completo.

**Como a equivalência é verificada.** A classe `TestesEquivalencia` executa as duas
árvores, com um pequeno avaliador de Álgebra Relacional em semântica de conjuntos,
sobre 40 bancos gerados aleatoriamente (com semente fixa). Cada uma das 26 consultas
precisa dar o mesmo resultado nas duas formas. Para validar o próprio teste, foram
inseridos bugs no otimizador, como separar `OR` como se fosse `AND`, e o teste os detectou.

### 6.7 Subconsultas

São aceitas subconsultas **não correlacionadas** no `WHERE` e no `FROM`.

#### No `WHERE`

Duas formas, como condição do `WHERE` ligada às demais por `AND`:

* `operando op_rel (SELECT coluna …)`, comparação com o valor da subconsulta;
* `operando IN (SELECT coluna …)`.

```bash
python main.py "SELECT nome FROM alunos WHERE idade > (SELECT idade FROM alunos WHERE id = 1);"
```

```
π_{nome}(alunos ⋉_{alunos.idade > sub1.idade} ρ_{sub1}(π_{idade}(σ_{id = 1}(alunos))))
```

![Árvore de consulta com subconsulta](docs/arvore_subconsulta.svg)

**Por que semijunção (`⋉`).** A Álgebra Relacional não tem subconsulta: a consulta
interna precisa virar uma relação combinada com a externa. A semijunção
`R ⋉_{θ} S` devolve as linhas de `R` para as quais existe alguma linha de `S`
que satisfaz `θ`, e **só com as colunas de `R`**. Por isso ela é a tradução
usual de `IN`. Comparada com `σ_{θ}(R × S)`:

* uma linha de `R` não se repete quando várias linhas de `S` a satisfazem;
* `SELECT *` continua devolvendo só as colunas da consulta externa;
* as colunas de `S` não se misturam com as de `R` acima da semijunção.

**Decisões da tradução:**

| Situação | Decisão |
|---|---|
| Nome da subconsulta | `ρ_{sub1}`, `ρ_{sub2}`…, nunca igual a uma tabela usada na consulta. No exemplo, o `ρ` é indispensável, porque `alunos` aparece nos dois níveis |
| `x IN (SELECT y …)` | condição `x = sub1.y` |
| Coluna sem tabela na condição θ | com uma tabela só no `FROM` externo, ela é qualificada (`idade` vira `alunos.idade`). Com várias, um nome igual ao da coluna da subconsulta gera erro pedindo para qualificar |
| Demais condições do `WHERE` | continuam num `σ` acima das semijunções |
| Subconsultas aninhadas | cada nível é traduzido da mesma forma, de fora para dentro |

**Diferença em relação ao SQL.** Se uma subconsulta de comparação devolver
**mais de uma linha**, o SQL dá erro (o SQLite usa a primeira linha). A semijunção
compara com todas, como `> ANY (…)`. Com zero ou uma linha, os resultados são
iguais: uma subconsulta vazia não deixa passar nenhuma linha, nos dois casos.

**Otimização (`--otimizar`).** Cada subconsulta é otimizada separadamente. Uma
seleção acima de `R ⋉ S` sempre pode descer para `R`, pois só as colunas de `R`
existem acima da semijunção. Projeções descem mantendo as colunas usadas na
condição θ.

**O que não é aceito** (todos geram erro semântico com a posição):

| Consulta | Motivo |
|---|---|
| `… WHERE x IN (SELECT y FROM b WHERE b.k = a.k)` | subconsulta correlacionada: exigiria descorrelacionar |
| `… WHERE x NOT IN (SELECT …)` | exigiria antijunção e o tratamento de `NULL` do `NOT IN` |
| `… WHERE EXISTS (SELECT …)` | em geral exige correlação |
| `… WHERE x = 1 OR x IN (SELECT …)` | dentro de `OR` ou `NOT`, a semijunção mudaria o resultado |
| `… JOIN b ON a.i IN (SELECT …)` | subconsulta no `ON` |
| `… IN (SELECT * …)` ou `… IN (SELECT y, z …)` | a subconsulta deve devolver uma coluna |

**Como a tradução é verificada.** `TestesSqlite` executa 26 consultas, com e sem
subconsulta (no `WHERE` e no `FROM`), no SQLite e nas duas árvores de Álgebra Relacional (canônica e
otimizada), sobre 30 bancos aleatórios, e exige o mesmo resultado. Nas
comparações, a subconsulta filtra pelo `id` de `a`, que é único, para devolver no
máximo uma linha, como o SQL exige. Para validar o próprio teste, foram inseridos
três bugs, e os três foram detectados:

* traduzir com junção em vez de semijunção;
* mandar a seleção para dentro da subconsulta;
* não qualificar a coluna externa.

#### No `FROM` (tabelas derivadas)

Uma consulta pode ocupar o lugar de uma tabela, com um apelido obrigatório:

```bash
python main.py "SELECT t.nome FROM (SELECT nome, idade FROM alunos WHERE idade > 18) t WHERE t.idade < 30;"
```

```
π_{t.nome}(σ_{t.idade < 30}(ρ_{t}(π_{nome, idade}(σ_{idade > 18}(alunos)))))
```

A tradução é direta: a subconsulta é traduzida normalmente, e o resultado
recebe o nome do apelido por uma renomeação `ρ_{t}`. Depois disso, ela se comporta
como qualquer tabela: pode entrar em `×`, em `JOIN … ON` e ter suas colunas
usadas como `t.coluna`. A subconsulta do `FROM` também pode conter subconsultas,
no `WHERE` ou no próprio `FROM`.

| Situação | Decisão |
|---|---|
| Apelido | obrigatório, como no SQL padrão. Ele é o nome usado no `ρ` |
| Colunas | podem ser várias, ou `*` quando o `FROM` interno tem uma tabela só |
| Verificação de colunas | como a lista de colunas da subconsulta é conhecida, `t.y` é rejeitado se a subconsulta não devolve `y`. Isso não é possível com tabelas comuns, sem esquema |
| Escopo | a subconsulta não enxerga as outras tabelas do `FROM` (não há `LATERAL`) |
| Otimização | a subconsulta é otimizada separadamente; seleções e projeções da consulta externa param acima do `ρ_{t}` |

Não são aceitos, com erro semântico:

| Consulta | Motivo |
|---|---|
| `… FROM (SELECT x FROM a)` | falta o apelido |
| `… FROM (SELECT * FROM a, b) t` | sem esquema, colunas com o mesmo nome nas duas tabelas não seriam detectadas |
| `… FROM (SELECT a.id, b.id FROM a, b) t` | duas colunas `id` ficariam com o mesmo nome depois do `ρ_{t}` |
| `… FROM b, (SELECT x FROM a WHERE a.k = b.k) t` | subconsulta correlacionada (exigiria `LATERAL`) |
| `SELECT t.y FROM (SELECT x FROM a) t` | a subconsulta não devolve `y` |

A comparação com o SQLite descrita acima inclui 8 consultas com tabelas
derivadas. Um bug colocado de propósito, que ignorava o `WHERE` e a projeção da
subconsulta do `FROM`, foi detectado.

---

## 7. Limitações e melhorias possíveis

**Limitações atuais:**

* Subconjunto de SQL: não há `DISTINCT`, `GROUP BY`/`HAVING`, agregações,
  `ORDER BY`, `UNION`/`INTERSECT`/`EXCEPT`, `IN` com lista de valores, `LIKE`,
  `BETWEEN`, `IS NULL`, expressões aritméticas, apelidos de colunas
  (`nome AS n`), `LEFT/RIGHT/FULL/NATURAL/CROSS JOIN` nem `JOIN … USING`.
* Subconsultas: só as não correlacionadas. No `WHERE`, como comparação ou `IN`,
  ligadas por `AND`; no `FROM`, como tabela derivada com apelido. Não há `EXISTS`,
  `NOT IN`, correlação, `LATERAL` nem subconsulta no `SELECT`. A comparação com
  subconsulta de várias linhas se comporta como `ANY` (seção 6.7).
* Sem esquema, uma coluna sem tabela dentro da subconsulta é considerada da
  própria subconsulta. Se ela fosse da consulta externa, a correlação não seria detectada.
* **Semântica de conjuntos × multiconjuntos:** a álgebra relacional clássica
  elimina duplicatas e o `SELECT` do SQL não. A tradução `π` equivale, a
  rigor, a `SELECT DISTINCT`.
* Sem catálogo (esquema): não dá para verificar se uma coluna existe,
  resolver colunas não qualificadas ambíguas em consultas com várias tabelas
  nem checar tipos (`idade = 'abc'`).
* A análise para no **primeiro** erro: não há recuperação com o token
  `error` do SLY.
* `SELECT *` com junções gera a expressão sem `π`, como manda a tradução
  canônica.

**Melhorias possíveis:**

* Reordenar as junções: o otimizador mantém a ordem do `FROM`, então em
  `FROM a, b, c WHERE a.x = c.x AND b.y = c.y` o produto `a × b` continua lá,
  embora outra ordem o evitasse. Fazer isso bem exige estimativas de custo.
* Receber um esquema (`{tabela: [colunas]}`) para validar colunas e qualificar
  automaticamente as não qualificadas. Isso também eliminaria os limites do
  otimizador descritos na seção 6.6.
* Ampliar a gramática com `DISTINCT` (π com/sem eliminação de duplicatas),
  `UNION` (∪), `EXCEPT` (−) e `GROUP BY` (operador γ).
* `NOT IN` e `NOT EXISTS` não correlacionados com antijunção (`▷`), e subconsultas
  correlacionadas por descorrelação.
* Gerar a saída também em LaTeX (`\pi_{nome}(\sigma_{idade \geq 18}(alunos))`).
* Recuperação de erros com produções `error` para relatar vários erros de uma vez.

---

## 8. Trabalho P2: atendimento ao enunciado

Esta seção relaciona cada item do enunciado do Trabalho P2 (Compiladores 2026/2)
com o lugar do projeto onde ele é atendido.

### 8.1 Checklist

| Item do enunciado | Onde está |
|---|---|
| 1. Pesquisar geradores de analisadores | seção 8.2 (SLY e comparação com FLEX/BISON e PLY) |
| 2. Executar um exemplo e não entregar uma calculadora | `calc.py` é o exemplo de partida; seção 8.3 compara os dois |
| 3. Prompt elaborado numa ferramenta de IA | seção 8.8 |
| 4a. Gerador escolhido e linguagem | seção 8.2: SLY, em Python |
| 4b. Onde estão as modificações: expressões regulares, produções, precedência, ambiguidade, ações semânticas, código de usuário | seção 8.4, e marcas `[NOVO]`/`[MODIFICADO]` no código |
| 4c. Tabela de produções e ações semânticas | seção 8.5 e `python main.py --producoes` |
| 4d. Árvore de derivação e árvore de derivação anotada | seção 8.6, `--anotada` e `--grafo-derivacao` |
| 4e. Exemplo executando o código | seção 8.7 (comandos para rodar ao vivo) |
| 5. Complexidade e ideia diferentes da calculadora | seção 8.3 |
| 6. Código-fonte com as modificações sinalizadas em comentários | seção 8.4 |

Ficam fora do código: o vídeo de até 7 minutos (há um roteiro na seção 8.9), a
formação do grupo, os encontros presenciais e a entrega pelo Teams.

### 8.2 Gerador escolhido: SLY (Python)

**SLY** (*Sly Lex-Yacc*), de David Beazley, gera analisadores léxicos e
sintáticos em Python 3. É o sucessor do PLY, do mesmo autor, e segue a mesma
ideia do par FLEX/BISON: um analisador léxico baseado em expressões regulares e
um analisador sintático **LALR(1)** gerado a partir de uma gramática livre de
contexto.

| | FLEX/BISON | PLY | SLY |
|---|---|---|---|
| Linguagem | C | Python | Python 3 |
| Onde fica a gramática | arquivos `.l` e `.y` separados | docstrings das funções | decorador `@_('...')` nos métodos de uma classe |
| Geração do analisador | etapa de compilação que gera código C | na execução, com cache em `parsetab.py` | na criação da classe (metaclasse), sem arquivo gerado |
| Algoritmo | LALR(1) | LALR(1) | LALR(1) |

Como o SLY é usado neste projeto:

* **Lexer** ([sql_ar/lexer.py](sql_ar/lexer.py)): a classe herda de `sly.Lexer`.
  O conjunto `tokens` declara os terminais; cada token é um atributo com uma
  expressão regular (`LE = r'<='`) ou um método decorado com `@_(regex)` quando
  precisa de ação (`ID`, `NUMBER`, `STRING`). O SLY junta os padrões **na ordem
  em que aparecem** num único regex mestre. Por isso `<=` vem antes de `<`.
  `ignore` e `ignore_*` descartam espaços e comentários, e `error()` trata
  caracteres inválidos.
* **Parser** ([sql_ar/parser.py](sql_ar/parser.py)): a classe herda de
  `sly.Parser`. Cada método decorado com `@_('lado direito')` é uma produção:
  o nome do método é o não terminal do lado esquerdo e o corpo é a ação
  semântica. Os valores dos símbolos são acessados por nome (`p.condicao`,
  `p.ID0`, `p.ID1`). `start` define o símbolo inicial, e `error()` trata erros
  de sintaxe. A tabela `precedence`, que o `calc.py` usa, não foi necessária
  (seção 3.1).
* Na criação da classe, o SLY monta a tabela LALR e informa os conflitos.
  Para esta gramática são **77 estados e 0 conflitos**.

### 8.3 Exemplo de partida e diferença para a calculadora

O exemplo executado e analisado primeiro foi a calculadora do SLY,
[calc.py](calc.py), mantida no repositório como referência. O tradutor
reaproveita **a estrutura** dela (uma classe `Lexer`, uma classe `Parser`, ações
nas produções e um laço interativo), mas o problema, a gramática e as ações
são outros.

| | `calc.py` | Tradutor SQL → Álgebra Relacional |
|---|---|---|
| Entrada | expressão aritmética | consulta SQL (`SELECT`, `FROM`, `WHERE`, `JOIN`, subconsultas no `WHERE` e no `FROM`) |
| Saída | um número | uma expressão da Álgebra Relacional (π, σ, ×, ⋈, ⋉, ρ) e as suas árvores |
| Tokens | 7 | 27 |
| Produções | 8 | 46 |
| Não terminais | 2 (`statement`, `expr`) | 18 |
| Estados LALR | 17 | 77 |
| Ambiguidade | gramática ambígua, resolvida com a tabela `precedence` | gramática não ambígua, com a precedência nos níveis `condicao` > `conjuncao` > `fator` |
| Recursão | `expr → expr + expr` | à esquerda (listas), à direita (`NOT`) e autoincorporação (parênteses e subconsultas) |
| Análise semântica | não há (só divisão por zero) | escopo de tabelas, apelidos, colunas qualificadas, subconsultas permitidas |
| Ações semânticas | calculam o número | constroem a AST, traduzida depois para uma árvore relacional |
| Além disso | — | otimização da árvore, árvores de derivação (simples e anotada), grafos em SVG, mensagens de erro com linha e coluna |

### 8.4 Onde estão as modificações

As marcas nos comentários seguem o pedido do item 6:

* `[NOVO]`: código que não existe no `calc.py`;
* `[MODIFICADO]`: parte que existe no `calc.py`, mas foi alterada.

Cada arquivo do pacote começa com uma dessas marcas. Para listar todas:

```bash
git grep -n -e "\[NOVO\]" -e "\[MODIFICADO\]"
```

| O que o enunciado pede mostrar | Onde está |
|---|---|
| Expressões regulares da análise léxica | [sql_ar/lexer.py](sql_ar/lexer.py): operadores relacionais, pontuação, `STRING`, `NUMBER`, `ID` e comentários |
| Palavras-chave sem diferença entre maiúsculas e minúsculas | `PALAVRAS_RESERVADAS` e o método `ID` em [sql_ar/lexer.py](sql_ar/lexer.py) |
| Produções da gramática | métodos `@_` de [sql_ar/parser.py](sql_ar/parser.py), descritos na seção 2 |
| Precedência e eliminação de ambiguidade | níveis `condicao` → `conjuncao` → `fator` (seção 3.1), no lugar da tabela `precedence` do `calc.py` |
| Ações semânticas | corpo e docstring de cada método `@_` em [sql_ar/parser.py](sql_ar/parser.py) (seção 8.5) |
| Tratamento de erros | `error()` do lexer e do parser `[MODIFICADO]`, e [sql_ar/semantica.py](sql_ar/semantica.py) `[NOVO]` |
| Código de usuário | os demais módulos de `sql_ar/` (AST, semântica, tradução, otimização, grafos e derivação) e [main.py](main.py) |

### 8.5 Tabela de produções e ações semânticas

Cada ação constrói o atributo sintetizado `.val` do não terminal do lado
esquerdo: um nó da AST ou uma lista. É uma definição **S-atribuída**, avaliada
de baixo para cima, na ordem das reduções do parser LR. Os índices (₁, ₂)
distinguem símbolos repetidos na mesma produção.

A tabela abaixo foi gerada por `python main.py --producoes`. As produções vêm da
gramática que o SLY montou e as regras vêm das docstrings das ações, então ela
acompanha o código. A numeração é a do SLY, que agrupa as alternativas de cada
não terminal.

| Nº | Produção | Regra semântica |
|---|---|---|
| 1 | `consulta → selecao fim` | `consulta.val = selecao.val` |
| 2 | `selecao → SELECT lista_selecao FROM lista_tabelas clausula_where` | `selecao.val = Consulta(lista_selecao.val, lista_tabelas.val, clausula_where.val)` |
| 3 | `fim → ε` | `fim: sem atributo (o ';' é opcional)` |
| 4 | `fim → SEMI` | `fim: sem atributo (o ';' é opcional)` |
| 5 | `clausula_where → ε` | `clausula_where.val = nulo` |
| 6 | `clausula_where → WHERE condicao` | `clausula_where.val = condicao.val` |
| 7 | `lista_selecao → lista_colunas` | `lista_selecao.val = lista_colunas.val` |
| 8 | `lista_selecao → STAR` | `lista_selecao.val = nulo (todas as colunas: não haverá π)` |
| 9 | `lista_colunas → coluna` | `lista_colunas.val = [coluna.val]` |
| 10 | `lista_colunas → lista_colunas COMMA coluna` | `lista_colunas.val = lista_colunas₁.val + [coluna.val]` |
| 11 | `coluna → referencia` | `coluna.val = referencia.val` |
| 12 | `referencia → ID DOT ID` | `referencia.val = Coluna(ID₂.lexema, tabela=ID₁.lexema)` |
| 13 | `referencia → ID` | `referencia.val = Coluna(ID.lexema)` |
| 14 | `lista_tabelas → item_from` | `lista_tabelas.val = [item_from.val]` |
| 15 | `lista_tabelas → lista_tabelas COMMA item_from` | `lista_tabelas.val = lista_tabelas₁.val + [item_from.val]` |
| 16 | `item_from → tabela` | `item_from.val = tabela.val` |
| 17 | `item_from → item_from INNER JOIN tabela ON condicao` | `item_from.val = Join(item_from₁.val, tabela.val, condicao.val)` |
| 18 | `item_from → item_from JOIN tabela ON condicao` | `item_from.val = Join(item_from₁.val, tabela.val, condicao.val)` |
| 19 | `tabela → subconsulta` | `tabela.val = TabelaDerivada(subconsulta.val, apelido=nulo) (rejeitado na análise semântica)` |
| 20 | `tabela → subconsulta AS ID` | `tabela.val = TabelaDerivada(subconsulta.val, apelido=ID.lexema)` |
| 21 | `tabela → subconsulta ID` | `tabela.val = TabelaDerivada(subconsulta.val, apelido=ID.lexema)` |
| 22 | `tabela → ID AS ID` | `tabela.val = Tabela(ID₁.lexema, apelido=ID₂.lexema)` |
| 23 | `tabela → ID ID` | `tabela.val = Tabela(ID₁.lexema, apelido=ID₂.lexema)` |
| 24 | `tabela → ID` | `tabela.val = Tabela(ID.lexema)` |
| 25 | `condicao → conjuncao` | `condicao.val = conjuncao.val` |
| 26 | `condicao → condicao OR conjuncao` | `condicao.val = Ou(condicao₁.val, conjuncao.val)` |
| 27 | `conjuncao → fator` | `conjuncao.val = fator.val` |
| 28 | `conjuncao → conjuncao AND fator` | `conjuncao.val = E(conjuncao₁.val, fator.val)` |
| 29 | `fator → comparacao` | `fator.val = comparacao.val` |
| 30 | `fator → EXISTS subconsulta` | `fator.val = Existe(subconsulta.val) (rejeitado na análise semântica)` |
| 31 | `fator → LPAREN condicao RPAREN` | `fator.val = condicao.val (os parênteses só agrupam)` |
| 32 | `fator → NOT fator` | `fator.val = Nao(fator₁.val)` |
| 33 | `comparacao → operando NOT IN subconsulta` | `comparacao.val = Em(operando.val, subconsulta.val, negado) (rejeitado na análise semântica)` |
| 34 | `comparacao → operando IN subconsulta` | `comparacao.val = Em(operando.val, subconsulta.val)` |
| 35 | `comparacao → operando op_rel operando` | `comparacao.val = Comparacao(operando₁.val, op_rel.val, operando₂.val)` |
| 36 | `op_rel → GE` | `op_rel.val = lexema do operador` |
| 37 | `op_rel → LE` | `op_rel.val = lexema do operador` |
| 38 | `op_rel → GT` | `op_rel.val = lexema do operador` |
| 39 | `op_rel → LT` | `op_rel.val = lexema do operador` |
| 40 | `op_rel → NE` | `op_rel.val = lexema do operador` |
| 41 | `op_rel → EQ` | `op_rel.val = lexema do operador` |
| 42 | `operando → subconsulta` | `operando.val = subconsulta.val` |
| 43 | `operando → STRING` | `operando.val = Texto(STRING.lexema)` |
| 44 | `operando → NUMBER` | `operando.val = Numero(NUMBER.lexema)` |
| 45 | `operando → referencia` | `operando.val = referencia.val` |
| 46 | `subconsulta → LPAREN selecao RPAREN` | `subconsulta.val = Subconsulta(selecao.val)` |

Depois da análise, a AST passa pela análise semântica e é traduzida para a
Álgebra Relacional pelas regras da seção 3.3. Na notação de tradução dirigida
pela sintaxe, com um atributo `.ar`, a tradução de `selecao` é:

```
selecao.ar = π_{lista_selecao.val}( σ_{clausula_where.val}( lista_tabelas.ar ) )
lista_tabelas.ar = item_from₁.ar × item_from₂.ar × …
item_from.ar = item_from₁.ar ⋈_{condicao.val} tabela.ar        (para JOIN … ON)
tabela.ar = ρ_{apelido}(nome)  ou  nome
```

Quando `lista_selecao.val` é nulo (`*`), não há π; quando `clausula_where.val` é
nulo, não há σ. As subconsultas viram semijunções (seção 6.7).

### 8.6 Árvore de derivação e árvore de derivação anotada

Para a sentença `SELECT nome, idade FROM alunos WHERE idade >= 18;`:

```bash
python main.py "SELECT nome, idade FROM alunos WHERE idade >= 18;" --grafo-derivacao derivacao.svg --abrir
```

O comando gera os dois grafos abaixo. A **árvore de derivação** mostra as
produções aplicadas, com os terminais nas folhas. O `ε` aparece quando é usada
uma produção vazia:

![Árvore de derivação](docs/derivacao.svg)

A **árvore de derivação anotada** acrescenta, em cada não terminal, o valor do
atributo `.val` calculado pela sua ação semântica. A recursão à esquerda aparece
nos três nós `lista_colunas`. Cada um aplica uma vez a regra 10 da tabela, e a
lista cresce de `[nome]` para `[nome, idade]`:

![Árvore de derivação anotada](docs/derivacao_anotada.svg)

A mesma árvore anotada em texto (`python main.py --anotada "…"`):

```
consulta.val = Consulta(colunas=[nome, idade], origem=[alunos], where=idade >= 18)
├── selecao.val = Consulta(colunas=[nome, idade], origem=[alunos], where=idade >= 18)
│   ├── "SELECT"
│   ├── lista_selecao.val = [nome, idade]
│   │   └── lista_colunas.val = [nome, idade]
│   │       ├── lista_colunas.val = [nome]
│   │       │   └── coluna.val = nome
│   │       │       └── referencia.val = nome
│   │       │           └── "nome"
│   │       ├── ","
│   │       └── coluna.val = idade
│   │           └── referencia.val = idade
│   │               └── "idade"
│   ├── "FROM"
│   ├── lista_tabelas.val = [alunos]
│   │   └── item_from.val = alunos
│   │       └── tabela.val = alunos
│   │           └── "alunos"
│   └── clausula_where.val = idade >= 18
│       ├── "WHERE"
│       └── condicao.val = idade >= 18
│           └── conjuncao.val = idade >= 18
│               └── fator.val = idade >= 18
│                   └── comparacao.val = idade >= 18
│                       ├── operando.val = idade
│                       │   └── referencia.val = idade
│                       │       └── "idade"
│                       ├── op_rel.val = ">="
│                       │   └── ">="
│                       └── operando.val = 18
│                           └── "18"
└── fim
    └── ";"
```

### 8.7 Demonstração (executar ao vivo)

Os comandos abaixo mostram, em ordem, o que o enunciado pede. Rode-os durante o
vídeo em vez de usar capturas de tela.

Tokens e tradução (análise léxica e sintática):

```bash
python main.py --tokens "SELECT nome, idade FROM alunos WHERE idade >= 18;"
```

Tabela de produções e ações semânticas:

```bash
python main.py --producoes
```

Árvore de derivação anotada, mostrando a recursão da lista de colunas:

```bash
python main.py --anotada "SELECT nome, idade, curso FROM alunos;"
```

Precedência (AND antes de OR, com parênteses):

```bash
python main.py --anotada "SELECT nome FROM alunos WHERE (curso = 'SI' OR curso = 'CC') AND idade > 18;"
```

Junção, subconsulta, otimização e grafos:

```bash
python main.py "SELECT a.nome FROM alunos a JOIN matriculas m ON a.id = m.aluno_id WHERE m.nota > 7 AND a.id IN (SELECT aluno_id FROM bolsas);" --otimizar --grafo arvore.svg --abrir
```

Erros léxico, sintático e semântico:

```bash
python main.py "SELECT nome FROM alunos WHERE idade > 1 # x"
```

```bash
python main.py "SELECT nome idade FROM alunos;"
```

```bash
python main.py "SELECT alunos.nome FROM alunos a;"
```

### 8.8 Prompt utilizado (item 3)

O projeto foi desenvolvido com o Claude Code a partir do prompt abaixo. Confira
se ele é o mesmo apresentado ao professor; se não for, substitua pelo prompt
apresentado.

<details>
<summary>Prompt inicial</summary>

```text
Atue como especialista em Compiladores, Gramáticas Livres de Contexto e Álgebra Relacional. Desenvolva um programa completo em Python que traduza consultas SQL para expressões da Álgebra Relacional, utilizando obrigatoriamente a biblioteca SLY, com "Lexer" e "Parser".

1. Explique primeiro a gramática, depois implemente o código.

Antes de programar, apresente a gramática formal em BNF ou EBNF, identificando terminais, não terminais, símbolo inicial e produções. Explique a análise léxica, sintática e semântica, com foco em autoincorporação (recursividade gramatical).

Demonstre a autoincorporação com uma produção como:

lista_colunas → lista_colunas , coluna
              | coluna

Explique a recursividade à esquerda, o caso-base, o caso recursivo e como essa regra reconhece listas de tamanho variável. Mostre derivações para consultas com várias colunas e identifique as produções recursivas no código SLY. Preserve a recursividade à esquerda quando apropriado, pois o SLY admite esse tipo de produção.

2. Implemente o tradutor.

O programa deve reconhecer:

- "SELECT", "FROM" e "WHERE";
- listas de colunas e tabelas separadas por vírgulas;
- "AND", "OR" e parênteses;
- operadores "=", "!=", "<>", "<", ">", "<=" e ">=";
- identificadores simples e qualificados, como "alunos.nome";
- "*", números e textos entre aspas simples;
- "JOIN ... ON", se possível dentro do escopo.

As palavras-chave devem aceitar maiúsculas e minúsculas. Utilize somente SLY para a análise léxica e sintática, sem substituir o parser por expressões regulares ou manipulação textual.

3. Traduza para Álgebra Relacional.

Utilize os operadores:

- Seleção: σ
- Projeção: π
- Produto cartesiano: ×
- Junção: ⋈
- Renomeação: ρ, quando necessária.

Exemplo:

Entrada:

SELECT nome, idade
FROM alunos
WHERE idade >= 18;

Saída:

π_{nome, idade}(σ_{idade >= 18}(alunos))

Garanta que a tradução preserve a estrutura lógica da consulta. Para condições compostas, defina uma gramática sem ambiguidades, com AND tendo precedência sobre OR e parênteses respeitados. Explique as decisões adotadas.

4. Requisitos do código.

Implemente:

- Lexer com tokens e tratamento de caracteres inválidos.
- Parser com produções gramaticais e ações semânticas.
- Construção das expressões relacionais a partir da estrutura sintática.
- Mensagens claras para erros léxicos e sintáticos.
- Interface simples para inserir consultas e visualizar os resultados.

Mantenha a gramática formal, o lexer e o parser consistentes. Prefira estruturas intermediárias organizadas a concatenações desordenadas de strings.

5. Testes obrigatórios.

Apresente consultas e resultados esperados para:

1. Uma coluna.
2. Múltiplas colunas.
3. "WHERE" com uma condição.
4. Condições com "AND".
5. Condições com "OR" e parênteses.
6. Duas tabelas com produto cartesiano e condição de junção.
7. "JOIN ... ON".
8. Consulta sintaticamente inválida.

Demonstre passo a passo a derivação de uma consulta com pelo menos três colunas e explique como a recursividade constrói a projeção. Mostre também como a precedência lógica é preservada.

6. Formato da resposta.

Apresente, nesta ordem:

1. Fundamentos da gramática e da autoincorporação.
2. Gramática formal completa.
3. Explicação da precedência e das ações semânticas.
4. Código Python completo e executável.
5. Instalação e execução.
6. Exemplos, derivações e testes.
7. Limitações e melhorias possíveis.

Antes de finalizar, revise a compatibilidade com a API real do SLY, os tokens, as produções, a recursividade e as ações semânticas. Não omita partes essenciais nem use pseudocódigo. Se não executar os testes, declare isso explicitamente.

Prioridade: produzir uma solução funcional, didática e academicamente correta, demonstrando claramente como uma gramática com autoincorporação reconhece consultas SQL e as traduz para Álgebra Relacional.
```

</details>

Pedidos seguintes, na ordem:

1. Gerar a árvore de consulta como grafo (a partir da imagem de uma árvore de consulta otimizada).
2. Adicionar a otimização, para o grafo ficar igual ao da imagem.
3. Revisar e completar a explicação de como executar o projeto no README.
4. Aceitar `SELECT` aninhado (subconsultas).
5. Conferir o projeto contra o enunciado do Trabalho P2 e implementar o que faltasse.

### 8.9 Roteiro sugerido para o vídeo (até 7 minutos)

| Tempo | Conteúdo | Apoio |
|---|---|---|
| 0:00–0:45 | Gerador escolhido (SLY, Python), como funciona e o prompt usado | seções 8.2 e 8.8 |
| 0:45–1:30 | Ponto de partida (`calc.py`) e o que mudou | seção 8.3 |
| 1:30–2:30 | Análise léxica: expressões regulares, palavras-chave e erros | `lexer.py` e `--tokens` |
| 2:30–3:45 | Gramática: produções, recursão, precedência sem ambiguidade | seções 2, 3.1 e `parser.py` |
| 3:45–4:45 | Ações semânticas e tabela de produções | `--producoes` |
| 4:45–5:45 | Árvore de derivação e árvore anotada | `--grafo-derivacao` |
| 5:45–7:00 | Execução: tradução, junção, subconsulta, otimização e erros | seção 8.7 |
