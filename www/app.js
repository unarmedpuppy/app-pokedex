// Load Pokemon data and card data
let pokemonList = [];
let cardData = {};

// Load Pokemon data and render grid
async function loadPokemon() {
    try {
        // Load Pokemon data
        const pokemonResponse = await fetch('/data/pokemon.json');
        pokemonList = await pokemonResponse.json();
        
        // Load card data (if available)
        try {
            const cardResponse = await fetch('/data/cards.json');
            cardData = await cardResponse.json();
        } catch (error) {
            console.warn('Card data not available:', error);
            cardData = {};
        }
        
        const grid = document.getElementById('pokemon-grid');
        
        pokemonList.forEach(pokemon => {
            const card = createPokemonCard(pokemon);
            grid.appendChild(card);
        });
    } catch (error) {
        console.error('Error loading Pokemon data:', error);
        document.getElementById('pokemon-grid').innerHTML = 
            '<p style="color: white; text-align: center; font-size: 1.5rem;">Error loading Pokemon data</p>';
    }
}

function createPokemonCard(pokemon) {
    const card = document.createElement('div');
    card.className = 'pokemon-card';
    card.dataset.pokemonNumber = pokemon.number;
    
    const inner = document.createElement('div');
    inner.className = 'pokemon-card-inner';
    
    // Front side (sprite)
    const front = document.createElement('div');
    front.className = 'pokemon-card-front';
    
    const number = document.createElement('div');
    number.className = 'pokemon-number';
    number.textContent = `#${pokemon.number.toString().padStart(3, '0')}`;
    
    const sprite = document.createElement('img');
    sprite.className = 'pokemon-sprite';
    const spriteName = pokemon.sprite_name || pokemon.name.toLowerCase().replace(/\s+/g, '-').replace(/'/g, '').replace(/\./g, '');
    sprite.src = `/sprites/${pokemon.number.toString().padStart(4, '0')}_${spriteName}.png`;
    sprite.alt = pokemon.name;
    sprite.onerror = function() {
        // Try alternative sprite name format
        const altName = pokemon.name.toLowerCase()
            .replace(/\s+/g, '-')
            .replace(/'/g, '')
            .replace(/\./g, '')
            .replace(/♀/g, '-f')
            .replace(/♂/g, '-m')
            .replace(/:/g, '');
        sprite.src = `/sprites/${pokemon.number.toString().padStart(4, '0')}_${altName}.png`;
        sprite.onerror = function() {
            card.classList.add('error');
        };
    };
    
    const name = document.createElement('div');
    name.className = 'pokemon-name';
    name.textContent = pokemon.name;
    
    front.appendChild(number);
    front.appendChild(sprite);
    front.appendChild(name);
    
    // Back side (card image)
    const back = document.createElement('div');
    back.className = 'pokemon-card-back';
    
    const cardImage = document.createElement('img');
    cardImage.className = 'pokemon-card-image';
    cardImage.alt = `${pokemon.name} TCG Card`;
    
    // Get card image URL if available
    const cardInfo = cardData[pokemon.number];
    if (cardInfo && cardInfo.card_image) {
        cardImage.src = cardInfo.card_image;
        cardImage.onerror = function() {
            back.innerHTML = `<div style="color: #666; padding: 20px;">No card image available<br>for ${pokemon.name}</div>`;
        };
    } else {
        back.innerHTML = `<div style="color: #666; padding: 20px;">No card data available<br>for ${pokemon.name}</div>`;
    }
    
    back.appendChild(cardImage);
    
    inner.appendChild(front);
    inner.appendChild(back);
    card.appendChild(inner);
    
    // Add click handler to flip card
    card.addEventListener('click', function() {
        card.classList.toggle('flipped');
    });
    
    return card;
}

// Load Pokemon when page loads
document.addEventListener('DOMContentLoaded', loadPokemon);

