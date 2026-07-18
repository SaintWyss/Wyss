# Phase 16 — Home Authority Core

## Objetivo

Yo mantengo identidad, conversación, planes, política A–D, confirmación, ejecución y auditoría en
Wyss. Home Edge sólo usa un contrato público local; no conoce executor ni bases internas.

## Límites

- Yo uso el socket Unix `0600` entre procesos locales y no abro puertos nuevos.
- Yo persisto idempotencia antes de procesar y cierro en ambiguo después de un crash.
- Yo mantengo B simple, C con `CONFIRMAR`, D absoluto y re-evaluación al resolver.
- Yo dejo transporte WSS, Projection Store y clientes físicos para los cortes dependientes.

## Evidencia esperada

- Suite, mypy estricto, Ruff, import-linter, web y Android verdes.
- Revisión profunda de seguridad y carreras antes del squash merge.
- ADR y documentación operativa alineados con el código.
