# Fil-Harness

**Agentes podem executar. Eles não podem conceder autoridade a si mesmos.**

**EN:** Agents may execute. They may not grant themselves authority.

[English version](README.en.md)

## Em 10 segundos

Fil-Harness é um **control plane local-first para agentes de código**. O agente pode produzir uma mudança, mas não pode usar a própria resposta — “PASS”, “ready”, “approved” — como prova de que o trabalho está correto ou autorizado.

O Harness separa três coisas que normalmente acabam misturadas:

```text
capacidade de executar ≠ evidência confiável ≠ autoridade para aprovar
```

## Por que existe

Agentes de código são bons em produzir candidatos. O problema aparece quando o mesmo sistema que fez a mudança também passa a ser tratado como a autoridade que certifica o resultado.

O Fil-Harness introduz uma fronteira explícita: **o provider executa; a verificação independente produz evidência; a política decide autoridade**.

## Como funciona

```text
Task Intake
    ↓
AgentProvider        saída não confiável/advisory
    ↓
Candidate commit
    ↓
Detached verification checkout
    ↓
TrustedRunner
    ↓
EvidenceEnvelope
    ↓
GateEngine
    ↓
Policy: ALLOW / HUMAN / DENY
```

## Diferenciais

- intake tipado com comportamento atual e desejado explícitos;
- `ScopeBudget` para limitar paths, quantidade de arquivos e LOC alteradas;
- seam provider-agnostic;
- worktree gravável separado do checkout de verificação detached;
- `TrustedRunner` com superfície de ações allowlisted;
- evidência ligada ao task, base SHA, candidate SHA, verification SHA e hashes de saída;
- gates determinísticos que **ignoram claims do provider**;
- unknown capabilities viram `DENY` por padrão;
- retry conservador para resultados ambíguos ou potencialmente side-effecting;
- estado durável em SQLite para tasks, runs, events, evidence, attempts e supervision checkpoints;
- supervisão genérica que continua subordinada à política do Harness.

## Regra de autoridade

A política classifica a próxima capacidade em:

- **ALLOW** — pode prosseguir automaticamente;
- **HUMAN** — exige decisão humana;
- **DENY** — não pode prosseguir.

Nem provider, nem supervisor, nem resposta humana transformam um `DENY` em `ALLOW`.

## Estado atual

Esta distribuição pública preserva o núcleo arquitetural do Harness em uma forma sanitizada e independente do laboratório privado.

Ela demonstra o modelo de autoridade, evidência, persistência, retry, isolamento de workspace e supervisão limitada. Não se apresenta como plataforma multi-agent completa, sandbox endurecido ou framework universal de governança de IA.

## Quick start

Requer Python 3.12+ e Git.

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

Demonstrações sintéticas:

```bash
python -m examples.bugfix_ready.run
python -m examples.human_gate.run
```

- `bugfix_ready` termina em `READY` somente depois de verificação confiável.
- `human_gate` termina em `WAITING_HUMAN` porque `merge` é uma capacidade classificada como humana mesmo quando o candidato já foi verificado.

## Claims do provider não são evidência

Os testes adversariais usam propositalmente providers que dizem coisas como `PASS`, `ready` e `approved`. Se a verificação independente falha, o candidato continua bloqueado.

Texto do provider nunca é inserido como trusted evidence.

## Limites

Fil-Harness não é:

- um sandbox hardened de VM/container;
- uma plataforma multi-agent completa;
- um produto de compliance enterprise;
- prova de que uma suíte de testes encontra todo defeito possível.

Ele é um control plane para **governar autoridade em torno da execução por agentes de código**.

## Segurança e trust model

Veja:

- [SECURITY.md](SECURITY.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/trust-model.md](docs/trust-model.md)
- [docs/public-private-boundary.md](docs/public-private-boundary.md)
