# Architecture Guidelines

Guidelines for architectural decisions in the IBTool project.

## Parameter Management

- **Avoid over-engineering**: Only create separate config files when parameters are shared across multiple modules
- **Keep local parameters local**: Define business logic parameters as class constants where they are used
- **YAGNI**: No abstractions until they are actually needed (2–3 parameters do not justify a config class)
- **`helpers/qgis_defaults.py`**: For technical QGIS parameters (buffer settings, precision) that must be consistent across tools
- **Single Source of Truth**: Each parameter is defined in exactly one place

## Class Design

- **Composition over inheritance**: Specialized classes that work together rather than complex inheritance hierarchies
- **Clear responsibilities**: Each class has exactly one purpose
- **Minimal constructors**: Config objects only when truly necessary — prefer simple initialization
- **Constants as class attributes**: `CLASS_CONSTANT = value` for parameters used only within that class

## Code Organization

- **Modular architecture**: Break large functions (500+ lines) into specialized classes with focused methods
- **No magic numbers**: All numeric constants must be named and documented
- **Eliminate redundancy**: If a parameter appears in multiple places, question whether it is truly shared or just duplicated
- **Pragmatic refactoring**: Always ask "Does this complexity serve a real purpose?" before adding abstractions

## File Organization

- **Group related functionality**: Use module directories (like `mst/`) for complex algorithms
- **Global utilities in `helpers/`**: Technical parameters, logging, geometry utils
- **Avoid config proliferation**: Do not create multiple config files for different purposes

## Usage Patterns

**QGIS Operations:**
```python
from helpers.qgis_defaults import QGISDefaults

qgis_defaults = QGISDefaults()
buffer_result = processing.run("native:buffer", {
    'SEGMENTS': qgis_defaults.buffer_segments,
    'END_CAP_STYLE': qgis_defaults.buffer_end_cap_style,
})
```

**Algorithm-specific parameters:**
```python
class StreetProcessor:
    ROAD_LENGTH_THRESHOLD = 50.0  # Business logic parameter

    def filter_short_streets(self, streets):
        expression = f'"length" < {self.ROAD_LENGTH_THRESHOLD}'
```

**Modular processing:**
```python
# Simple initialization — no config objects needed
processor = StreetProcessor()
calculator = MSTCalculator()

# Clean workflow orchestration
mst_creator = CreateMST()
result = mst_creator.calculate_mst(buildings, streets, crs)
```
