# Command Spec #
There are two different types of commands:
- mode switches: switches into sub command menu
- commands: actual commands

Each mode offers these commands:
- help: show available commands for the current mode
- back: go back to parent mode 
- exit: quit
- cls: clear screen

# Main mode #
Path: main

## mode switches ##
- dev: Graph development
- exec: execute graphs and assistants
- llm: LLM mode
- server: select a server and more
- settings: local CLI settings

## commands ##
- version

# Dev mode #
Path: main:dev

Notes: 
- Dev mode requires the CLI is started within a langgraph code repository to work with.

## mode switches ##
- select: select an existing graph to work with

## commands ##
- list: list all graphs from the current repo
- create: create a new graph with LLM guidance
- status: Show git status
- commit: commit all changes

# Selected graph mode #
Path: main:dev:[graph_id]:[LLM mode]

Notes:
- User interacts with LLM to apply changes to the selected graph
- User can switch between different LLM modes

## mode switches ##
- normal: asks for confirmation before every potentially destructive operation: file edits, bash commands, and similar. You review and approve each change one at a time.
- plan: restricted to read-only tools (Read, Glob, Grep, LS, WebSearch, WebFetch, Task, AskUserQuestion) and cannot call Edit, Write, or Bash.
- auto: executes file edits without prompting, letting it work uninterrupted

## commands ##
- compile: compile the selected graph
- delete: delete the selected graph
- preview: visualize the selected graph
- status: see above
- commit: see above

# Exec mode #
Path: main:exec[server name]

Notes:
- requires a selected server
- commands and mode switches must be disabled if no server is selected

## mode switches ##
- select: select a graph

## commands ##
- list: list all available graphs
- deploy: Commit, push, and reload agents on the server (for langosh server only)

# Graph mode #
Path: main:exec[server name]:[graph_id]

Notes:
- Requires a selected graph_id

## mode switches ##
- select: select an assistant
- thread: select a thread (for the current graph)

## commands ##
- create: create a new assistant with custom context
- search: search for assistants
- show: display the graph
- test: creates a stateless run for the selected graph
- run: creates a stateful run for the selected graph (default assistant)
- threads: list all threads to the current graph

For run command, prompt the user with the following questions:
- execution mode: background, stream output, wait for output
- create new thread: yes/no
- if new thread = no -> select a thread

Note: graph_id and optionally assistant_id is stored in thread metadata. This allows us to find threads by graph.

# Assistant mode #
Path: main:exec[server name]:[graph_id]:[assistant_id]

Notes:
- Requires a selected assistant

## mode switches ##
- thread: select a thread (for the current assistant)

## commands ##
- show: display assistant details
- update: update assistant context
- delete: delete the assistant
- test: see above
- run: see above
- threads: list all threads to the current assistant

# Thread mode #
Path: main:exec[server name]:[graph_id]:[assistant_id]:[thread_id]

Notes:
- Requires a selected graph and optionally an assistant_id

## commands ##
- details: show thread details
- state: show the thread state
- history: show the thread history
- delete: delete the thread
- update: update the thread, requires user input
- runs: list runs for a thread
- select: select a run_id

# Run mode #
Path: main:exec[server name]:[graph_id]:[assistant_id]:[thread_id]:[run_id]

Notes:
- Requires a selected thread_id

## commands ##
- details: get details for a specific run, requires run_id
- delete: delete a run, requires run_id
- cancel: cancel a specific run by run_id

# LLM mode #
Path: main:llm

## mode switches ##
- chat: chat with LLM
- code: LLM can call tools

## commands ##
- models: List all models with filter
- fetchmodels: Refresh model list from APIs
- use: select a LLM model

# Chat mode #
Path: main:llm[model name]:chat

## commands ##
- clear: clears conversation history
- compact: compact conversation history

# Code mode #
Path: main:llm[model name]:code

## commands ##
- clear: clears conversation history
- compact: compact conversation history

# Server mode #
Path: main:server

Note: no server selected

## commands ##
- list: list all configured servers
- select: select a server from the list
- add: add a server
- update: update a server
- delete: delete a serve

Servers are defined by: name, url

# Selected Server mode #
Path: main:server:[server name]

Note: automatically used when a server was selected.

## mode switches ##
- config: show and edit server config
- apikeys: show and edit API keys for CLI auth

## commands ##
- list: see above
- select: see above
- info: server version, graphs, status
- reload: hot-reload agent repo (langosh server only)

# Server Config mode #
Path: main:server:[server name]:config

Note: applies only to langosh servers

## commands ##
- show: show server configuration
- reset: reset entire server configuration
- configure: configure server config step by step 

# Server API-Keys mode #
Path: main:server:[server name]:api-keys

Note: applies only to langosh servers

## commands ##
- list: list all API keys
- create: create an API key
- delete: delete an API key
- rotate: rotate an API key

# Settings mode #
Path: main:settings

## commands ##
- show: show all settings
- configure: starts a conversation to update all settings except servers 


