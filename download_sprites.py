#!/usr/bin/env python3
"""
Download all Pokemon sprites.
"""

import json
import os
import requests
import time

def normalize_pokemon_name(name):
    """Convert Pokemon name to lowercase for sprite URL."""
    special_cases = {
        "Nidoran♀": "nidoran-f",
        "Nidoran♂": "nidoran-m",
        "Farfetch'd": "farfetchd",
        "Mr. Mime": "mr-mime",
        "Mime Jr.": "mime-jr",
        "Type: Null": "type-null",
        "Tapu Koko": "tapu-koko",
        "Tapu Lele": "tapu-lele",
        "Tapu Bulu": "tapu-bulu",
        "Tapu Fini": "tapu-fini",
        "Mr. Rime": "mr-rime",
        "Sirfetch'd": "sirfetchd",
        "Flabébé": "flabebe",
    }
    
    if name in special_cases:
        return special_cases[name]
    
    normalized = name.lower()
    normalized = normalized.replace(" ", "-")
    normalized = normalized.replace("'", "")
    normalized = normalized.replace(".", "")
    normalized = normalized.replace(":", "")
    normalized = normalized.replace("♀", "-f")
    normalized = normalized.replace("♂", "-m")
    return normalized

def download_sprite(pokemon, output_dir):
    """Download a Pokemon sprite with fallback URLs."""
    sprite_name = pokemon.get('sprite_name') or normalize_pokemon_name(pokemon['name'])
    
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
                source_name = url.split('/')[-3]  # Extract source name from URL
                print(f"  ✓ {pokemon['name']} (#{pokemon['number']}) - {source_name}")
                return True
        except Exception as e:
            continue  # Try next source
    
    # If all sources failed
    print(f"  ✗ {pokemon['name']} (#{pokemon['number']}) - All sources failed")
    return False

def main():
    """Main function."""
    # Load Pokemon list
    with open('data/pokemon.json', 'r') as f:
        pokemon_list = json.load(f)
    
    # Create sprites directory
    os.makedirs('sprites', exist_ok=True)
    
    # Download sprites
    print(f"Downloading {len(pokemon_list)} sprites...")
    success_count = 0
    for pokemon in pokemon_list:
        if download_sprite(pokemon, 'sprites'):
            success_count += 1
        time.sleep(0.1)  # Be nice to the server
    
    print(f"\nDownloaded {success_count}/{len(pokemon_list)} sprites")

if __name__ == '__main__':
    main()

