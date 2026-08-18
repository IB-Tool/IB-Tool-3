# Terminology and References

Canonical definition of *what* IB-Tool 3 delineates and *which publication
covers which part of the method*. All other documents in this repository link
here instead of restating it — if a definition or a citation changes, it changes
here.

---

## What IB-Tool 3 delineates

IB-Tool 3 approximates the **Innenbereich** as defined in **§ 34 BauGB** — the
coherently built-up part of a municipality (*im Zusammenhang bebauter
Ortsteil*), within which a building application is assessed against the
surrounding development rather than against a binding land-use plan.

The delineation is **morphological and data-driven**: it is derived from
building footprints, the road network and land use. It is an **approximation**,
not a legal determination — the binding Innenbereich is established by the
competent authority in the individual case. IB-Tool 3 produces a uniform,
reproducible baseline for settlement monitoring and planning support.

---

## "Innenbereich" vs. "Urban Growth Boundary (UGB)"

The German legal term *Innenbereich* has no direct English equivalent. In the
international publication of the method (Harig et al. 2021) the same geometry is
therefore described as an **Urban Growth Boundary (UGB)**, because that is the
concept an international readership recognises.

The UGB wording originates **solely** in that 2021 journal article and is a
choice of communication, not of substance. The dissertation (Harig 2024) does
not use the term at all — it works exclusively with the Innenbereich under
§ 34 BauGB. So if you are looking for the UGB framing in the dissertation, you
will not find it, and that is not an inconsistency.

Both terms denote the same delineation in this documentation. They are, however,
**not synonyms in general usage**:

|  | Innenbereich (§ 34 BauGB) | Urban Growth Boundary |
|---|---|---|
| Nature | Descriptive legal status of the **existing** built-up area | In most international literature: a planning **instrument** — a policy-set limit for **future** growth |
| Established by | Follows from the facts on the ground, assessed case by case | Adopted by a planning authority |
| Role here | The object IB-Tool 3 approximates | Only used when referring to Harig et al. (2021) and the international literature |

**Rule for this documentation:** use **Innenbereich** in running text, with
"(§ 34 BauGB)" on first mention per document. Use **UGB** only where the
international publication or international literature is being referenced, and
state there that it denotes the same delineation. Do not introduce further
variants ("settlement boundary", "settlement delineation") as if they were
defined terms.

---

## References — which source covers what

| Source | What it covers |
|---|---|
| **Harig, O.; Hecht, R.; Burghardt, D.; Meinel, G. (2021).** *Automatic Delineation of Urban Growth Boundaries Based on Topographic Data Using Germany as a Case Study.* ISPRS Int. J. Geo-Inf. **10**(5), 353. https://doi.org/10.3390/ijgi10050353 | The **method**: processing pipeline, algorithms, the empirically derived thresholds (e.g. BCR > 18 %), and the accuracy validation against expert delineations. **Cite this if you use IB-Tool 3 in research.** |
| **Harig, O. (2024).** *Automatisierte Abgrenzung von Innenbereichen einschließlich Ergebnisevaluierung — Grundlage für ein Siedlungsflächenmonitoring.* TU Dresden, Faculty of Environmental Sciences. | The **legal grounding in § 34 BauGB** and the **parameterisation** of the method — Chap. 4.4 (methodology), Chap. 4.5 (parameterisation), App. A.1.3 (expert survey). |
| **Harig, O. (2021).** *Toolset for the delineation of settlements on the basis building footprints, road network and land use data* (v1.0). https://doi.org/10.26084/IOERFDZ-SOFT-001 | The **original toolset** from which IB-Tool 3 and the `ibtoolpartion` plugin are derived. |
| **Eichhorn, S.; Harig, O.; …; Hecht, R. (2025).** *Assessing the suitability of settlement delineations for monitoring infilling: A web- and GIS-based expert evaluation approach.* Environ. Plan. B Urban Anal. City Sci. **52**(7). https://doi.org/10.1177/23998083241308407 | **Evaluation** of automated delineations for infill monitoring — methodological quality and practical applicability. |

Supporting planning literature used for individual thresholds:

- Bukies, M.; Meyer, G.; Rabe, H. (2009): *Abgrenzung des Innenbereichs im unbeplanten Siedlungsgebiet.*
- Spannowsky et al. (2020, 2022): *Baugesetzbuch — Commentary on § 34 BauGB.*

---

## Related documents

- [how-it-works.md](how-it-works.md) — concept, pipeline, algorithms
- [parameterization.md](parameterization.md) — parameters and their sources
- [../README.md](../README.md) — overview and how to cite
