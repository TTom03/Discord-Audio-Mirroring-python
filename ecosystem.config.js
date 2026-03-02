module.exports = {
  apps: [
    {
      name: 'voice-bridge',
      script: './bot.py',
      interpreter: './venv/bin/python',
      cwd: '/home/voice-bridge-stable',
      env: {
        NODE_ENV: 'production',
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      error_file: '/home/voice-bridge-stable/logs/error.log',
      out_file: '/home/voice-bridge-stable/logs/out.log',
      log_file: '/home/voice-bridge-stable/logs/combined.log',
      time: true,
    },
  ],
};
