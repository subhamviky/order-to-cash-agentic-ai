# Design documents

| Document | Word | Covers |
|---|---|---|
| [Order-to-Cash Agentic AI — Design](O2C_DESIGN.md) | [docx](O2C_Design_Document.docx) | `o2c-agent-service`: HLD (context, framework fit, Google Cloud deployment, integration and contracts, identity, model access) and LLD (data, class model and contracts, sequences, states, failure model, configuration, verification, gaps) |

The document follows the structure of the E2A design documents (`e2a-framework/docs/design/`), the A2C, G2C and P0 designs (`a2c-framework/docs/design/`) and the managed-provider designs (`e2a-managed-providers/docs/design/`), and refers to them rather than repeating them.

Diagrams are in `diagrams/` (Graphviz `.dot`, PlantUML `.puml` with `common/style.puml`) and rendered to `images/`:

```
dot -Tpng -Gdpi=220 diagrams/<name>.dot -o images/<name>.png
java -jar plantuml.jar -tpng -o ../images diagrams/<name>.puml
```
