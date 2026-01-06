# Servizio - Voice Ordering System

A production-ready voice ordering system for boba shops built with **FastAPI**, **Twilio**, and **Deepgram Agent API**. Features real-time voice conversations, SMS notifications, and live order dashboards.

## What is Servizio?

Servizio is an AI-powered voice ordering system that allows customers to call a phone number and place boba tea orders through natural conversation. The system uses advanced speech recognition, natural language processing, and text-to-speech to create a seamless ordering experience.

### Key Features

-  **Natural Voice Ordering**: Customers call and speak naturally to place orders
-  **AI-Powered Assistant**: Uses Deepgram's Agent API for intelligent conversation
-  **SMS Notifications**: Automatic order confirmations and ready notifications
-  **Real-time Dashboards**: Live order tracking for staff and customers
-  **Production Ready**: Containerized, scalable, and secure


## Demo

### How It Works

1. **Customer calls** your Twilio phone number
2. **AI greets** them: "Hey! I am your Servizio. What would you like to order?"
3. **Natural conversation** - Customer says: "I want a taro milk tea with boba"
4. **AI confirms** order details and asks for phone number
5. **Order placed** - Customer receives SMS confirmation with order number
6. **Staff sees** order on dashboard and prepares it
7. **Ready notification** - Customer gets SMS when order is ready

### Sample Conversation

```
Customer: "Hi, I'd like to order a taro milk tea with boba"
AI: "One taro milk tea with boba. Is that correct?"
Customer: "Yes, that's right"
AI: "Great! Would you like anything else?"
Customer: "No, that's all"
AI: "Can I please get your phone number for this order?"
Customer: "555-123-4567"
AI: "Thank you! Your order number is 4782. We'll text you when it's ready for pickup!"
```


### Core Components

- **FastAPI Backend**: REST API + WebSocket bridge for audio streaming
- **Deepgram Agent**: Real-time speech-to-text, LLM reasoning, text-to-speech
- **Twilio Integration**: Voice calls + SMS notifications
- **Real-time Dashboard**: Server-Sent Events for live order updates
- **Containerized**: Podman/Docker with production-ready configuration

## Quick Start

### Prerequisites

- Python 3.11+
- Podman or Docker
- ngrok (for local testing)
- Twilio account with A2P 10DLC approval
- Deepgram API key


## Project Structure

```
Servizio/
├── app/                          # Main application code
│   ├── main.py                   # FastAPI application entrypoint
│   ├── app_factory.py            # Application factory with lifecycle hooks
│   ├── settings.py               # Configuration and environment variables
│   ├── http_routes.py            # REST endpoints (Twilio webhooks, dashboards)
│   ├── ws_bridge.py              # WebSocket bridge for Twilio ↔ Deepgram audio
│   ├── agent_client.py           # Deepgram Agent API client
│   ├── agent_functions.py        # AI tool definitions and state management
│   ├── business_logic.py         # Core business logic (menu, cart, orders)
│   ├── orders_store.py           # Thread-safe JSON persistence layer
│   ├── events.py                 # Pub/sub system for real-time updates
│   ├── audio.py                  # Audio format conversion (µ-law ↔ Linear16)
│   ├── send_sms.py               # Twilio SMS integration
│   ├── session.py                # User session management
│   ├── call_logger.py            # Call logging and debugging
│   ├── order_ids.py              # Order ID generation utilities
│   └── orders.json               # Order storage (auto-reset on startup)
│
├── documentations/               # Comprehensive configuration
├── podman-start.sh               # Local development script
├── podman-stop.sh                # Cleanup script
├── requirements.txt              # Python dependencies
├── sample.env.txt                # Environment variables template
└── README.md                     # This file
```

### Key Components

- **`app/`** - Core application logic and API endpoints
- **`Containerfile`** - Container configuration for easy deployment
- **`sample.env.txt`** - Template for environment configuration



## Technical Details

### Audio Processing Pipeline

1. **Twilio Input**: µ-law 8kHz audio from phone calls
2. **Resampling**: Convert to Linear16 48kHz for Deepgram
3. **Deepgram Processing**: STT → LLM reasoning → TTS
4. **Output**: Convert back to µ-law 8kHz for Twilio

### AI Agent Configuration

- **STT Model**: `flux-general-en` (real-time speech recognition)
- **LLM Model**: `gemini-2.5-flash` (reasoning and responses)
- **TTS Model**: `aura-2-odysseus-en` (natural voice synthesis)
- **Language**: English (`en`)

### State Management

- **Session-based**: Each call maintains isolated state
- **Thread-safe**: Concurrent call handling with proper locking
- **Persistent**: Orders stored in JSON with automatic cleanup
- **Real-time**: Live updates via Server-Sent Events

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Landing page |
| `/voice` | POST | Twilio webhook (call initiation) |
| `/twilio` | WS | WebSocket for audio streaming |
| `/orders` | GET | TV dashboard (large display) |
| `/barista` | GET | Staff console interface |
| `/orders.json` | GET | Orders data (JSON API) |

## Development Workflow

### Code Organization

- **Separation of Concerns**: Clear separation between HTTP routes, WebSocket handling, business logic, and AI integration
- **Dependency Injection**: Settings and services injected through FastAPI's dependency system
- **Error Handling**: Comprehensive error handling with proper HTTP status codes
- **Logging**: Structured logging for debugging and monitoring

### Debugging Tools

- **Call Logger**: Automatic logging of all call interactions
- **Order Tracking**: Complete order lifecycle logging
- **WebSocket Monitoring**: Real-time connection status
- **Error Reporting**: Detailed error messages with stack traces

## Production Considerations

### Performance

- **Concurrent Calls**: Supports multiple simultaneous calls
- **Memory Management**: Efficient audio processing with minimal memory footprint
- **Connection Pooling**: Optimized database and API connections

### Security

- **API Key Management**: Secure environment variable handling
- **Input Validation**: Comprehensive request validation
- **Rate Limiting**: Built-in protection against abuse
- **HTTPS**: SSL/TLS encryption for all communications

### Scalability

- **Horizontal Scaling**: Stateless design allows multiple instances
- **Load Balancing**: Compatible with standard load balancers
- **Database**: Easy migration to persistent database (PostgreSQL, etc.)


