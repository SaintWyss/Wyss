"""Corpus dorado sintetico para el gate hit@1 de busqueda hibrida.

Mapeo auditable topico -> documento -> queries:
- cocina -> /golden/personal/risotto_azafran.md -> q01, q02, q03
- cocina -> /golden/ragcorp/focaccia_levadura.md -> q04, q05
- astronomia -> /golden/personal/quasar_redshift.md -> q06, q07, q08
- astronomia -> /golden/ragcorp/pulsar_magnetar.md -> q09, q10
- finanzas -> /golden/personal/arbitraje_cupon.md -> q11, q12, q13
- finanzas -> /golden/ragcorp/balance_dividendos.md -> q14, q15
- jardineria -> /golden/personal/hidroponia_perlita.md -> q16, q17, q18
- jardineria -> /golden/ragcorp/compost_lombriz.md -> q19, q20

Los keywords distintivos de cada documento no aparecen en otros topicos. FakeEmbedding es
ruido determinista; estas consultas deben ser inequívocas solo con FTS5/BM25.
"""

CORPUS: tuple[tuple[str, str, str], ...] = (
    (
        "/golden/personal/risotto_azafran.md",
        "Risotto de azafran con carnaroli, manteca fria y caldo reducido al final.",
        "personal",
    ),
    (
        "/golden/ragcorp/focaccia_levadura.md",
        "Focaccia de levadura madre con salmuera, alveolos grandes y romero fresco.",
        "ragcorp",
    ),
    (
        "/golden/personal/quasar_redshift.md",
        "Quasar lejano medido por redshift alto y espectro de absorcion estable.",
        "personal",
    ),
    (
        "/golden/ragcorp/pulsar_magnetar.md",
        "Pulsar cercano comparado con magnetar joven por rafagas de radio periodicas.",
        "ragcorp",
    ),
    (
        "/golden/personal/arbitraje_cupon.md",
        "Arbitraje de bonos con cupon escalonado, duration corta y spread controlado.",
        "personal",
    ),
    (
        "/golden/ragcorp/balance_dividendos.md",
        "Balance trimestral con dividendos aprobados, EBITDA positivo y caja neta.",
        "ragcorp",
    ),
    (
        "/golden/personal/hidroponia_perlita.md",
        "Hidroponia casera con perlita lavada, solucion nutritiva y bandeja profunda.",
        "personal",
    ),
    (
        "/golden/ragcorp/compost_lombriz.md",
        "Compost maduro con lombriz roja, humus tamizado y restos vegetales secos.",
        "ragcorp",
    ),
)
