FROM nginx:alpine

LABEL version="1.0.7" build-date="2026-01-10"

# Copy web files
COPY www/ /usr/share/nginx/html/
COPY data/ /usr/share/nginx/html/data/
COPY sprites/ /usr/share/nginx/html/sprites/

# Expose port 80
EXPOSE 80

# Nginx will start automatically

