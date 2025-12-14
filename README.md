# Pokédex

A minimalist web application displaying all Pokémon in National Pokédex order with their sprites, names, and numbers.

## Access

- **URL**: https://pokedex.server.unarmedpuppy.com
- **Port**: 8103 (direct access, optional)
- **Status**: ✅ ACTIVE

## Features

- Complete National Pokédex display
- Grid layout with responsive design
- Pokemon sprites from Pokémon Database
- Minimalist, clean interface

## Setup

### 1. Install Dependencies

```bash
cd apps/pokedex
pip3 install -r requirements.txt
```

### 2. Generate Pokemon Data and Download Sprites

Run the complete setup script to fetch all Pokemon from PokeAPI and download sprites:

```bash
python3 setup_pokemon_data.py
```

This script will:
- Fetch all 1025 Pokemon from PokeAPI (Gen 1-9)
- Create `data/pokemon.json` with complete Pokemon list
- Download all sprites to `sprites/` directory

**Note**: This may take 10-15 minutes to complete as it downloads 1025 sprites.

### Alternative: Quick Setup (Gen 1 only)

For a quick test with just Gen 1 Pokemon (151 Pokemon):

```bash
python3 generate_pokemon_list.py
python3 download_sprites.py
```

### 3. Build and Run

```bash
docker compose build
docker compose up -d
```

The app will be available at:
- https://pokedex.server.unarmedpuppy.com (via Traefik)
- http://localhost:8095 (direct access)

## Data Files

- `data/pokemon.json` - Complete list of all Pokemon with numbers and names
- `sprites/` - Directory containing all Pokemon sprite images

## References

- [Serebii National Pokédex](https://www.serebii.net/pokemon/nationalpokedex.shtml)
- [Pokémon Database Sprites](https://img.pokemondb.net/sprites/scarlet-violet/normal/)

