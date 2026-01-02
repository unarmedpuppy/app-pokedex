# Pokedex - Agent Instructions

Minimalist web application displaying the complete National Pokedex.

## Overview

Static web app showing all 1025 Pokemon (Gen 1-9) with:
- Grid layout with sprites
- Pokemon numbers and names
- Card flip animation with TCG cards
- Responsive design

**Port**: 8103

## Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | Static HTML/CSS/JS |
| Data | JSON + local sprites |
| Container | Nginx (static serving) |
| Data Source | PokeAPI |

## Project Structure

```
pokedex/
├── www/                       # Web frontend
│   ├── index.html
│   ├── style.css
│   └── script.js
├── data/
│   └── pokemon.json           # Pokemon data (name, number)
├── sprites/                   # Downloaded sprite images
├── setup_pokemon_data.py      # Fetches all data + sprites
├── requirements.txt           # Python dependencies
├── Dockerfile
└── docker-compose.yml
```

## Quick Commands

```bash
# Generate/update Pokemon data (first time setup)
pip3 install -r requirements.txt
python3 setup_pokemon_data.py    # Takes 10-15 minutes

# Local Docker build
docker compose up -d --build

# Access at http://localhost:8103
```

## Data Generation

The `setup_pokemon_data.py` script:
1. Fetches all 1025 Pokemon from PokeAPI
2. Creates `data/pokemon.json` with complete list
3. Downloads all sprites to `sprites/` directory

**Note**: Initial setup takes 10-15 minutes to download all sprites.

### Manual Data Update
```bash
# Re-fetch if new Pokemon are added
python3 setup_pokemon_data.py
docker compose build --no-cache && docker compose up -d
```

## Data Format

`data/pokemon.json`:
```json
[
  {"number": 1, "name": "Bulbasaur"},
  {"number": 2, "name": "Ivysaur"},
  ...
]
```

Sprites stored as: `sprites/{number}.png` (e.g., `sprites/25.png` for Pikachu)

## Deployment

### Via home-server
```bash
# Deployed at: home-server/apps/pokedex/
cd ~/server/apps/pokedex
docker compose up -d
```

### CI/CD
Images auto-built via GitHub Actions on tag push:
```bash
git tag v1.0.0
git push --tags
```

### Registry
```bash
docker pull registry.server.unarmedpuppy.com/pokedex:latest
```

## Configuration

No runtime configuration needed - fully static site.

### Dockerfile
- Multi-stage build copies www/, data/, sprites/ to Nginx
- Serves on port 80 internally

## Boundaries

### Always Do
- Run `setup_pokemon_data.py` after PokeAPI updates
- Use `--no-cache` when rebuilding with new data
- Verify sprites downloaded successfully before deploying

### Ask First
- Adding interactive features
- Changing data structure
- Integrating additional APIs

### Never Do
- Commit the entire sprites/ directory (use .gitignore)
- Hardcode Pokemon data (use the JSON file)
- Remove existing Pokemon

## Data Sources

- **PokeAPI**: https://pokeapi.co/ - Pokemon data
- **Pokemon Database**: Sprite images
- **Serebii**: National Pokedex reference

## See Also

- [Root AGENTS.md](../AGENTS.md) - Cross-project conventions
- [README.md](./README.md) - Setup details
