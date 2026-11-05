FROM node:26 AS build

# Add build argument for the API URL
ARG VITE_API_URL

# Set it as an environment variable
ENV VITE_API_URL=$VITE_API_URL

WORKDIR /app
COPY package*.json /app/
RUN npm ci

COPY . /app
RUN npm run build

FROM nginx:1.29-alpine

COPY --from=build /app/dist /usr/share/nginx/html/
COPY srv/nginx.conf /etc/nginx/nginx.conf
COPY srv/mime.types /etc/nginx/mime.types

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
