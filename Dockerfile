FROM nginx:alpine

# Create directories
RUN mkdir -p /usr/share/nginx/html/data /usr/share/nginx/html/sprites

# Copy web files
COPY www/ /usr/share/nginx/html/

# Copy data and sprites (if they exist)
COPY data/ /usr/share/nginx/html/data/ 2>/dev/null || true
COPY sprites/ /usr/share/nginx/html/sprites/ 2>/dev/null || true

# Expose port 80
EXPOSE 80

# Nginx will start automatically

