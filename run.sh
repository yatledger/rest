#!/bin/zsh
tmux new-session -d 'cd api && uvicorn --port 9696 --reload main:app'
tmux split-window -h 'npm run dev'
tmux -2 attach-session -d