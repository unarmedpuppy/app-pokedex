# Pokédex

A minimalist web application displaying all Pokémon in National Pokédex order with their sprites, names, and numbers.

## Features

- Complete National Pokédex display (1025 Pokémon)
- Grid layout with responsive design
- Pokemon sprites from Pokémon Database
- Minimalist, clean interface
- Card flip animation with Pokemon TCG cards

## Quick Start

### Local Development

```bash
# Build and run locally
docker compose up --build

# Access at http://localhost:8103
```

### Generate/Update Pokemon Data

```bash
# Install dependencies
pip3 install -r requirements.txt

# Run complete setup (fetches all Pokemon + sprites)
python3 setup_pokemon_data.py
```

This will:
- Fetch all 1025 Pokemon from PokeAPI (Gen 1-9)
- Create `data/pokemon.json` with complete Pokemon list
- Download all sprites to `sprites/` directory

**Note**: Initial setup takes 10-15 minutes to download all sprites.

## Docker Image

This app is published to a private registry:

```bash
# Pull the image
docker pull registry.server.unarmedpuppy.com/pokedex:latest

# Run it
docker run -p 8103:80 registry.server.unarmedpuppy.com/pokedex:latest
```

### Building and Publishing

Images are automatically built and pushed via GitHub Actions when you create a tag:

```bash
git tag v1.0.0
git push --tags
```

Or manually trigger a build via the Actions tab.

## Data Files

- `data/pokemon.json` - Complete list of all Pokemon with numbers and names
- `sprites/` - Directory containing all Pokemon sprite images
- `www/` - Web frontend (HTML, CSS, JS)

## References

- [Serebii National Pokédex](https://www.serebii.net/pokemon/nationalpokedex.shtml)
- [Pokémon Database Sprites](https://img.pokemondb.net/sprites/scarlet-violet/normal/)
- [PokeAPI](https://pokeapi.co/)
