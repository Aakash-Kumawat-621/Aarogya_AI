# Aarogya AI — Knowledge Base Specification
**Last updated: Module 3**

## Design principle
The KB is category-scoped but registry-driven — adding a new disease category
requires only a one-line entry in `DISEASE_CATEGORIES` below and a new MeSH
query. No code changes to the retriever or chain are needed.

---

## Disease scope (Module 3 MVP)

| # | Category | MeSH terms |
|---|---|---|
| 1 | Cardiovascular | "chest pain"[MeSH], "cardiac arrhythmia"[MeSH], "heart failure"[MeSH], "hypertension"[MeSH], "myocardial infarction"[MeSH] |
| 2 | Respiratory | "pneumonia"[MeSH], "asthma"[MeSH], "pulmonary disease, chronic obstructive"[MeSH], "tuberculosis"[MeSH], "COVID-19"[MeSH] |
| 3 | Gastrointestinal | "abdominal pain"[MeSH], "appendicitis"[MeSH], "gastritis"[MeSH], "irritable bowel syndrome"[MeSH], "peptic ulcer"[MeSH] |
| 4 | Musculoskeletal | "fractures, bone"[MeSH], "sprains and strains"[MeSH], "joint diseases"[MeSH], "back pain"[MeSH] |
| 5 | Dermatological | "skin diseases"[MeSH], "rash"[MeSH], "wound infection"[MeSH], "burns"[MeSH] |
| 6 | Neurological | "headache"[MeSH], "migraine disorders"[MeSH], "dizziness"[MeSH], "seizures"[MeSH] |
| 7 | Infectious (India-relevant) | "dengue"[MeSH], "malaria"[MeSH], "typhoid fever"[MeSH], "leptospirosis"[MeSH], "chikungunya"[MeSH] |
| 8 | Endocrine | "diabetes mellitus, type 2"[MeSH], "thyroid diseases"[MeSH], "hypoglycemia"[MeSH] |

**Excluded from MVP:** rare diseases (<1 per million), pediatric-only conditions,
surgical procedures, psychiatric conditions, oncology.

**Future categories (to add):** Ophthalmology, ENT, Nephrology, Obstetrics,
Psychiatry. Adding a new category = 1 line in `DISEASE_CATEGORIES` dict +
PubMed re-run.

---

## Pinecone index structure

| Namespace | Source | Chunk size | Overlap | Target vectors |
|---|---|---|---|---|
| `medical-kb` | PubMed abstracts + MedMCQA | 512 tokens | 50 tokens | 60,000 |
| `drug-db` | OpenFDA labels + adverse events | 256 tokens | 0 tokens | 30,000 |
| `hospital-db` | Doctor/hospital stubs | 256 tokens | 0 tokens | 10,000 |

**Index config:** dimension=768, metric=cosine (BioSentBERT output)

---

## PubMed quality filters

- Publication date: 2018–2024
- Language: English only
- Population: humans only (`humans[mh]`)
- Must have abstract (`hasabstract[text]`)
- Min abstract length: 150 words
- Exclude: case reports, editorials, animal studies
- Include: clinical trials, systematic reviews, original research

---

## Chunk metadata schema (per chunk)

```json
{
  "text": "...",
  "source": "pubmed | openfda | medmcqa",
  "pmid": "12345678",
  "disease_category": "cardiovascular",
  "year": 2022,
  "chunk_index": 0,
  "drug_name": null
}
```

---

## Target fetch counts

| Source | Target records | Est. chunks |
|---|---|---|
| PubMed | 5,000 abstracts | ~55,000 |
| MedMCQA | 10,000 QA pairs | ~10,000 |
| OpenFDA drug labels | 3,000 labels | ~18,000 |
| OpenFDA adverse events | 2,000 events | ~8,000 |
