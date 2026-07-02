<a id="readme-top"></a>

<div align="center">
  <h3 align="center">Resilient Regression Testing</h3>

  <p align="center">
    Python-only, YAML-driven regression runner for IBM SOAR / Resilient scenarios with dry-run and real API modes.
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
    <li>
      <a href="#scenario-authoring">Scenario Authoring</a>
      <ul>
        <li><a href="#supported-actions">Supported Actions</a></li>
        <li><a href="#pre-defined-variables">Pre-defined Variables</a></li>
        <li><a href="#validation">Validation</a></li>
        <li><a href="#examples">Examples</a></li>
      </ul>
    </li>
    <li><a href="#testing">Testing</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->
## About The Project

Resilient Regression Testing runs declarative YAML scenarios against IBM SOAR / Resilient incident workflows. It can create or target incidents, apply ordered actions, validate final incident state, report pass/fail results, and clean up incidents created during a run.

Use dry-run mode for local mock execution. Use real mode with direct IBM Resilient credentials to create, update, fetch, validate, and close real SOAR incidents through `resilient-circuits`.

### Built With

* [![Python][Python]][Python-url]
* [![uv][uv]][uv-url]
* [![pytest][pytest]][pytest-url]
* [![Pydantic][Pydantic]][Pydantic-url]
* [![PyYAML][PyYAML]][PyYAML-url]
* [![Rich][Rich]][Rich-url]
* [![resilient-circuits][ResilientCircuits]][ResilientCircuits-url]

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- GETTING STARTED -->
## Getting Started

### Prerequisites

* Python 3.10+
* [uv](https://docs.astral.sh/uv/)

### Installation

```sh
uv sync
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- USAGE EXAMPLES -->
## Usage

Run one YAML file in dry-run mode:

```sh
uv run resilient-regression run scenarios/example.yaml --dry-run
```

Run every `.yaml` / `.yml` file in a directory in dry-run mode:

```sh
uv run resilient-regression run scenarios --dry-run
```

Run against a real IBM SOAR / Resilient instance with API key credentials:

```sh
uv run resilient-regression run scenarios --host https://soar.example.test --org 201 --api-key-id KEY_ID --api-key-secret KEY_SECRET
```

Run against a real IBM SOAR / Resilient instance with username/password credentials:

```sh
uv run resilient-regression run scenarios --host https://soar.example.test --org 201 --user-name user@example.test --password PASSWORD
```

Write a JSON report:

```sh
uv run resilient-regression run scenarios/example.yaml --dry-run --report-json reports/latest.json
```

Mode and option rules:

| Flag | Purpose |
|---|---|
| `--dry-run` | Use the local mocked SOAR client. Does not require credentials. |
| `--host URL` | IBM SOAR / Resilient host URL for real mode. |
| `--org ORG` | IBM SOAR / Resilient organization id for real mode. |
| `--api-key-id KEY_ID` | API key id for real mode. Requires `--api-key-secret`. |
| `--api-key-secret KEY_SECRET` | API key secret for real mode. Requires `--api-key-id`. |
| `--user-name USER` | Username for real mode. Requires `--password`. |
| `--password PASSWORD` | Password for real mode. Requires `--user-name`. |
| `--no-cleanup` | Skip cleanup for incidents created during the run. |
| `--report-json PATH` | Write structured run results to JSON. |
| `--verbose` | Print step-level execution output. |

Real mode creates the API client with `resilient_circuits.rest_helper.get_resilient_client(opts)`. Provide either `--api-key-id`/`--api-key-secret` or `--user-name`/`--password`; partial or mixed credential sets fail before scenarios run. Secrets are not printed in setup errors or reports.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- SCENARIO AUTHORING -->
## Scenario Authoring

A YAML file can contain one or more scenarios. Each scenario can use list-style syntax or mapping-style syntax.

Use list-style syntax for scenarios that create their own incident:

```yaml
scenario-name:
  - step name:
      create-inc:
        name: Example Incident
  - validate:
      name: Example Incident
```

Use mapping-style syntax when you need scenario metadata such as `allow_failure` or `incident_id`:

```yaml
scenario-name:
  allow_failure: true
  incident_id: 1
  steps:
    - step name:
        update-inc:
          properties.owner: tier2
  validate:
    properties.owner: tier2
```

`incident_id` targets an existing incident instead of creating a new one. The scenario fails if that incident does not exist. This is useful for tests that update fields, add notes, update tasks, run scripts, or close a pre-existing incident.

`allow_failure` marks a known-broken scenario as non-fatal to the overall suite. The scenario still reports as an allowed failure.

Cleanup stays scoped to incidents created during the current run. Scenario-provided `incident_id` values are never auto-cleaned. In dry-run mode cleanup deletes mock incidents; in real mode cleanup deletes created incidents with `PUT /incidents/delete` and a JSON array of incident IDs. Use `--no-cleanup` to skip cleanup, which is shown in the report.

### Supported Actions

| YAML action | Dry-run mode | Real mode |
|---|---|---|
| `create-inc` | Creates a mock incident and stores `${incident.*}` variables. | Creates a real incident. |
| `update-inc` | Updates the current or targeted mock incident. | Updates the current or targeted real incident with PATCH-style payloads. |
| `close-incident` | Sets incident close/status fields. | Updates/ closes the real incident. |
| `wait-before-run` | Parses duration but does not sleep. | Sleeps before the next action. |
| `validate` | Reads mock incident state and applies assertions. | Fetches latest real incident state and applies assertions. |
| `add-note` | Appends a mock note. | Not supported yet; fails clearly. |
| `add-task` | Appends a mock task and stores `${task.*}` variables. | Not supported yet; fails clearly. |
| `update-task` | Updates latest mock task or explicit task `id`. | Not supported yet; fails clearly. |
| `run-script` | Records a mock script run with inputs/result. | Dry-run only; fails clearly. |

### Pre-defined Variables

Variables can be used in action values. Incident and task values are intentionally separate.

| Variable | Source | Notes |
|---|---|---|
| `${incident.id}` | Latest created, updated, closed, or targeted incident | Different from task id |
| `${incident.name}` | Latest incident `name` | Different from task name |
| `${incident.status}` | Latest incident `status` | Defaults to `Active`, becomes `Closed` after close |
| `${task.id}` | Latest created or updated task | Different from incident id |
| `${task.name}` | Latest task `name` | Different from incident name |
| `${task.status}` | Latest task `status` | Defaults to `Open` unless specified |

### Validation

Validation supports dotted paths, list indexes, and the normalized `incident.` prefix.

Examples:

* `properties.field_1`
* `type_ids`
* `incident.type_ids`
* `notes.0.text`
* `tasks.0.status`
* `script_runs.0.result.score`

Supported comparison functions:

| Comparison | Passes when | Example |
|---|---|---|
| equality shorthand | Actual value equals expected value. | `name: Expected Name` |
| `equals` | Actual value equals expected value. | `status: { equals: Closed }` |
| `contains` | Actual list, tuple, set, string, dict key, or dict value contains expected value. | `type_ids: { contains: phishing }` |
| `exists` | Path exists when `true`; path is missing when `false`. | `id: { exists: true }` |
| `not_null` | Path exists and value is not `null`. | `properties.owner: { not_null: true }` |
| `is_null` | Path is missing or value is `null`. | `properties.optional: { is_null: true }` |

Example validation block using each comparison:

```yaml
validate:
  name: Expected Name
  status:
    equals: Closed
  type_ids:
    contains: phishing
  id:
    exists: true
  properties.owner:
    not_null: true
  properties.optional:
    is_null: true
```

### Examples

#### 1. Simple: create an incident and verify it exists

```yaml
create-basic-incident:
  - create basic incident:
      create-inc:
        name: Basic Created Incident
        description: Verifies the mock runner can create an incident
  - validate:
      id:
        exists: true
      name: Basic Created Incident
```

#### 2. Simple: update an existing incident by `incident_id`

```yaml
existing-incident-id-updates-existing-record:
  incident_id: 1
  steps:
    - update existing incident owner:
        update-inc:
          properties.owner: tier2
    - close existing incident:
        close-incident:
          status: Closed
          resolution: Re-validated via explicit incident_id
  validate:
    id: 1
    status: Closed
    resolution: Re-validated via explicit incident_id
    properties.owner: tier2
```

#### 3. More complex dry-run: notes, tasks, script run, and close

```yaml
workflow-note-task-script-close:
  - create phishing incident:
      create-inc:
        name: Phishing Regression Incident
        properties.severity: High
        type_ids:
          - phishing
  - add opening note with incident variables:
      add-note:
        text: "Created ${incident.name} with incident id ${incident.id}"
  - add triage task with incident variables:
      add-task:
        name: "Triage ${incident.name}"
        status: Open
  - mark triage task complete using task id variable:
      update-task:
        id: "${task.id}"
        status: Complete
        resolution: triaged
  - run enrichment script with incident and task variables:
      run-script:
        name: Mock Enrichment Script
        inputs:
          incident_id: "${incident.id}"
          task_id: "${task.id}"
        result:
          enriched: true
          score: 95
  - close incident with resolution:
      close-incident:
        status: Closed
        resolution: Resolved by dry-run regression
  - validate:
      status: Closed
      resolution: Resolved by dry-run regression
      properties.severity: High
      type_ids:
        contains: phishing
      notes.0.text: "Created Phishing Regression Incident with incident id 1"
      tasks.0.status: Complete
      script_runs.0.result.score: 95
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- TESTING -->
## Testing

Run unit tests:

```sh
uv run pytest
```

Tests cover YAML loading, dotted-path validation, scenario execution, mock and real client selection, real client payloads, supported actions, variable interpolation, existing incident targeting, allowed failures, unsupported real-mode actions, secret-safe config errors, and cleanup after failure.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ROADMAP -->
## Roadmap

- [x] Local dry-run runner with mocked incident store
- [x] YAML scenario loader and Pydantic validation
- [x] Terminal and JSON reports
- [x] Notes, tasks, script runs, close actions, and explicit `incident_id`
- [x] Real IBM SOAR client for create, update, fetch, validate, close, and delete cleanup
- [ ] Real notes, tasks, and script execution support
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
[ResilientCircuits]: https://img.shields.io/badge/resilient--circuits-052FAD?style=for-the-badge&logo=ibm&logoColor=white
[ResilientCircuits-url]: https://pypi.org/project/resilient-circuits/
