# Voice runtime extraction

`volvox_voice.agent.run_agent` contains the same Pipecat worker flow previously embedded in `bot.py`. `bot.py` imports it and remains the supported Windows CLI entry point. This module has a Pipecat 1.12.0 dependency and is currently coupled to the repository model paths and CLI response output. The capture/Whisper adapter remains in the root `local_speech.py` pending a transport-neutral interface.
