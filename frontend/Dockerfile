FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

# Production port for Dokploy; override with PORT env if needed
ENV PORT=3334
EXPOSE 3334

CMD ["npm", "run", "dev"]
