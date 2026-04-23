# PNG Character Setup Instructions

## Required PNG Files

Copy the following PNG files to `frontend/src/assets/agents/`:

```bash
# Navigate to project root where PNG files are located
cd /Users/gunno/Desktop/projects/traider-phase1

# Copy all PNG characters
cp head_trader.png         frontend/src/assets/agents/analyst.png
cp risk_manager.png        frontend/src/assets/agents/risk_manager.png
cp performance_analyst.png frontend/src/assets/agents/weekly.png
cp researcher.png          frontend/src/assets/agents/monthly.png
cp reflector.png           frontend/src/assets/agents/reflector.png
cp news_agent_.png         frontend/src/assets/agents/news_agent.png
cp system_supervisor.png   frontend/src/assets/agents/supervisor.png
cp system_maintenance.png  frontend/src/assets/agents/maintenance.png
cp communication_agent_2.png frontend/src/assets/agents/notify.png
```

## Verify Files

After copying, verify all files exist:

```bash
ls -la frontend/src/assets/agents/
```

Expected output:
```
analyst.png
risk_manager.png
weekly.png
monthly.png
reflector.png
news_agent.png
supervisor.png
maintenance.png
notify.png
```

## Implementation Complete

✅ AgentActivity.jsx updated with new AGENTS_CONFIG  
✅ CSS updated with PNG character styles (mix-blend-mode: screen)  
✅ Head Office layout updated  
✅ Desk grid (3 columns)  
✅ Support grid (4 columns with 5 agents)  
✅ Hover animations added  
✅ Responsive design (2 columns < 1400px)  

## Test After Setup

1. Copy PNG files (see commands above)
2. Start frontend: `npm run dev`
3. Navigate to Agent Activity page
4. Verify:
   - All characters display without black boxes
   - Glow effects work (based on agent color)
   - Hover animations work
   - All 9 agents visible (1 head office + 3 desk + 5 support)
   - No console errors about missing images
