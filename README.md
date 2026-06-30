<a id="readme-top"></a>

<div align="center">
  <h3 align="center">Resilient Regression Testing</h3>

  <p align="center">
    Python-only, YAML-driven dry-run regression runner for IBM SOAR / Resilient scenarios.
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#scenario-format">Scenario Format</a></li>
    <li><a href="#testing">Testing</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->
## About The Project

Resilient Regression Testing runs declarative YAML scenarios against a local mocked IBM SOAR incident store. It creates and updates mock incidents, validates final incident state, reports pass/fail results, and cleans up created incidents at the end.

Milestone 1 is intentionally dry-run only. It does not connect to a real IBM SOAR instance.

### Built With

* [![Python][Python]][Python-url]
* [![uv][uv]][uv-url]
* [![pytest][pytest]][pytest-url]
* [![Pydantic][Pydantic]][Pydantic-url]
* [![PyYAML][PyYAML]][PyYAML-url]
* [![Rich][Rich]][Rich-url]

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- GETTING STARTED -->
## Getting Started

### Prerequisites

* Python 3.10+
* [uv](https://docs.astral.sh/uv/)

### Installation

Install dependencies:

```sh
uv sync
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- USAGE EXAMPLES -->
## Usage

Run one scenario file:

```sh
uv run resilient-regression run scenarios/example.yaml --dry-run
```

Run every `.yaml` / `.yml` file in a directory:

```sh
uv run resilient-regression run scenarios --dry-run
```

Write JSON report:

```sh
uv run resilient-regression run scenarios/example.yaml --dry-run --report-json reports/latest.json
```

Skip cleanup:

```sh
uv run resilient-regression run scenarios/example.yaml --dry-run --no-cleanup
```

Show step-level output:

```sh
uv run resilient-regression run scenarios/example.yaml --dry-run --verbose
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- SCENARIO FORMAT -->
## Scenario Format

One YAML file can contain many tests:

```yaml
create-test-1:
  - create-basic-incident:
      create-inc:
        name: Create Test 1
  - validate:
      id:
        exists: true
      name: Create Test 1

create-test-2:
  - create-basic-incident:
      create-inc:
        name: Create Test 2
  - validate:
      id:
        exists: true
      name: Create Test 2
```

One directory can also contain many YAML files. Passing the directory runs all of them.

`allow_failure` marks known-broken scenarios as non-fatal to the suite:

```yaml
known-broken-test:
  allow_failure: true
  steps:
    - create-basic-incident:
        create-inc:
          name: Known Broken Incident
    - validate:
        name: Expected Different Name
```

Original list-style syntax remains supported:

```yaml
test-abc:
  - step-1:
      create-inc:
        name: Test Incident
        description: Regression test
        properties.field_1: field_1_val
        type_ids:
          - expected_incident_type_val
  - step-2:
      wait-before-run: 10 sec
      update-inc:
        properties.field_5: expected_val_field_5
  - validate:
      properties.field_5: expected_val_field_5
      incident.type_ids:
        contains: expected_incident_type_val
```

Supported step actions:

* `create-inc`
* `update-inc`
* `wait-before-run` (parsed, but not slept in dry-run mode)
* `validate`

Supported validation assertions:

* equality shorthand: `properties.field_1: expected`
* `equals`
* `contains`
* `exists`
* `not_null`
* `is_null`

Dotted paths support `properties.field_1`, `type_ids`, and normalized `incident.type_ids`.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- TESTING -->
## Testing

Run unit tests:

```sh
uv run pytest
```

Tests cover YAML loading, dotted-path validation, scenario execution, and cleanup after failure.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ROADMAP -->
## Roadmap

- [x] Local dry-run runner with mocked incident store
- [x] YAML scenario loader and Pydantic validation
- [x] Terminal and JSON reports
- [ ] Real IBM SOAR API client
- [ ] Additional scenario actions and assertions

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- LICENSE -->
## License

No license file is included yet.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ACKNOWLEDGMENTS -->
## Acknowledgments

* README style inspired by [Best-README-Template](https://github.com/othneildrew/Best-README-Template).

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
[Python]: https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white
[Python-url]: https://www.python.org/
[uv]: https://img.shields.io/badge/uv-DE5FE9?style=for-the-badge&logo=python&logoColor=white
[uv-url]: https://docs.astral.sh/uv/
[pytest]: https://img.shields.io/badge/pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white
[pytest-url]: https://docs.pytest.org/
[Pydantic]: https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=pydantic&logoColor=white
[Pydantic-url]: https://docs.pydantic.dev/
[PyYAML]: https://img.shields.io/badge/PyYAML-FFD43B?style=for-the-badge&logo=yaml&logoColor=black
[PyYAML-url]: https://pyyaml.org/
[Rich]: https://img.shields.io/badge/Rich-000000?style=for-the-badge&logo=python&logoColor=white
[Rich-url]: https://rich.readthedocs.io/
