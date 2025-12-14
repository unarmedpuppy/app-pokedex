#!/usr/bin/env python3
"""
Complete setup script: Fetch all Pokemon from PokeAPI and download sprites.
This is the main script to run to set up the Pokedex data.
"""

import json
import os
import requests
import time

def normalize_pokemon_name(name):
    """Convert Pokemon name to lowercase for sprite URL."""
    special_cases = {
        "nidoran-f": "nidoran-f",
        "nidoran-m": "nidoran-m",
        "farfetchd": "farfetchd",
        "mr-mime": "mr-mime",
        "mime-jr": "mime-jr",
        "type-null": "type-null",
        "tapu-koko": "tapu-koko",
        "tapu-lele": "tapu-lele",
        "tapu-bulu": "tapu-bulu",
        "tapu-fini": "tapu-fini",
        "mr-rime": "mr-rime",
        "sirfetchd": "sirfetchd",
        "flabebe": "flabebe",
    }
    
    name_lower = name.lower().replace(" ", "-")
    if name_lower in special_cases:
        return special_cases[name_lower]
    
    return name_lower

def format_display_name(api_name):
    """Convert API name to display name."""
    # PokeAPI uses lowercase with hyphens, convert to proper case
    parts = api_name.split('-')
    display_name = ' '.join(word.capitalize() for word in parts)
    
    # Handle special cases
    special_cases = {
        "Nidoran F": "Nidoran♀",
        "Nidoran M": "Nidoran♂",
        "Farfetch D": "Farfetch'd",
        "Mr Mime": "Mr. Mime",
        "Mime Jr": "Mime Jr.",
        "Type Null": "Type: Null",
    }
    
    if display_name in special_cases:
        return special_cases[display_name]
    
    return display_name

def fetch_all_pokemon():
    """Fetch all Pokemon from PokeAPI."""
    print("Fetching Pokemon list from PokeAPI...")
    pokemon_list = []
    
    # PokeAPI has 1025 Pokemon as of Gen 9
    total = 1025
    for i in range(1, total + 1):
        try:
            url = f"https://pokeapi.co/api/v2/pokemon/{i}/"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                api_name = data['name']
                display_name = format_display_name(api_name)
                sprite_name = normalize_pokemon_name(api_name)
                
                pokemon_list.append({
                    'number': i,
                    'name': display_name,
                    'sprite_name': sprite_name
                })
                
                if i % 50 == 0:
                    print(f"  Fetched {i}/{total}...")
            else:
                print(f"  Error fetching #{i}: HTTP {response.status_code}")
        except Exception as e:
            print(f"  Error fetching #{i}: {e}")
        
        # Be nice to the API
        if i % 20 == 0:
            time.sleep(0.5)
    
    return pokemon_list

def download_sprite(pokemon, output_dir):
    """Download a Pokemon sprite with fallback URLs."""
    sprite_name = pokemon['sprite_name']
    
    output_path = os.path.join(output_dir, f"{pokemon['number']:04d}_{sprite_name}.png")
    
    # Skip if already exists
    if os.path.exists(output_path):
        return True
    
    # Try multiple sprite sources in order
    sprite_sources = [
        f"https://img.pokemondb.net/sprites/scarlet-violet/normal/{sprite_name}.png",
        f"https://img.pokemondb.net/sprites/brilliant-diamond-shining-pearl/normal/{sprite_name}.png",
        f"https://img.pokemondb.net/sprites/bank/normal/{sprite_name}.png",
        f"https://img.pokemondb.net/sprites/home/normal/{sprite_name}.png",
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    for url in sprite_sources:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                return True
        except Exception as e:
            continue  # Try next source
    
    # If all sources failed
    return False

def main():
    """Main function."""
    os.makedirs('data', exist_ok=True)
    os.makedirs('sprites', exist_ok=True)
    
    # Step 1: Fetch Pokemon list
    print("=" * 60)
    print("Step 1: Fetching Pokemon list from PokeAPI")
    print("=" * 60)
    pokemon_list = fetch_all_pokemon()
    
    # Save to JSON
    json_path = 'data/pokemon.json'
    with open(json_path, 'w') as f:
        json.dump(pokemon_list, f, indent=2)
    print(f"\n✓ Saved {len(pokemon_list)} Pokemon to {json_path}")
    
    # Step 2: Download sprites
    print("\n" + "=" * 60)
    print("Step 2: Downloading Pokemon sprites")
    print("=" * 60)
    print(f"Downloading {len(pokemon_list)} sprites...")
    
    success_count = 0
    for i, pokemon in enumerate(pokemon_list, 1):
        if download_sprite(pokemon, 'sprites'):
            success_count += 1
        
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(pokemon_list)} ({success_count} successful)")
        
        time.sleep(0.1)  # Be nice to the server
    
    print(f"\n✓ Downloaded {success_count}/{len(pokemon_list)} sprites")
    print("\nSetup complete!")

if __name__ == '__main__':
    main()

