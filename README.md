

# form2yaml

A simple web-based tool for generating YAML configurations from Jinja2 templates and structured form definitions.

It provides a dynamic UI driven by `template.meta.yaml`, allowing users to define inputs, render templates, preview output, and export YAML files.

---

## Features

- Dynamic form generation from YAML schema (`template.meta.yaml`)
- Jinja2-based YAML rendering
- Live preview of generated YAML
- Download generated configuration
- Snapshot support (save & reload form state)
- Easy extensibility via `functions.py`

---

## Project Structure

```
form2yaml/
├── app/
│   ├── main.py
│   ├── functions.py
│   ├── templates_ui/
│   └── static/
│
├── templates/
│   └── example-basic/
│       ├── template.meta.yaml
│       └── template.yaml.j2
│
├── Dockerfile
├── Makefile
├── README.md
```

---

## Requirements

- Docker
- make (optional, but recommended)

---

## Quick Start

### Build

```
make build
```

### Run

```
make up
```

Application will be available at:

```
http://localhost:8000
```

---

## How It Works

1. Templates are loaded from the `templates/` directory
2. Each template contains:
   - `template.meta.yaml` → defines the form
   - `template.yaml.j2` → defines the output
3. User fills the form in the UI
4. Data is converted into a context (`ctx`)
5. Jinja2 renders the final YAML

---

## Creating a New Template

1. Create a new directory inside `templates/`

```
templates/my-template/
```

2. Add:

```
template.meta.yaml
template.yaml.j2
```

3. Restart the app

---

## Example

### template.meta.yaml

```
meta_version: 1
id: example
name: Example Template

sections:
  main:
    label: Basic
    fields:
      name:
        label: Name
        type: string
        required: true
```

### template.yaml.j2

```
name: {{ main.name }}
```

---

## Custom Functions

You can extend Jinja2 with your own helper functions.

Edit:

```
app/functions.py
```

Example:

```
def to_upper(value):
    return str(value).upper()
```

Then use in template:

```
name: {{ main.name | to_upper }}
```

---

## Snapshots

Snapshots allow you to save and reload form state.

Saved to:

```
snapshots/<template>/<name>.yml
```

---

## Development

If you modify backend code:

```
make build
make up
```

---

## Philosophy

This project is intentionally:

- simple
- template-driven
- framework-light
- easy to extend

It is not tied to any specific domain.

---

## License

MIT (or your preferred license)