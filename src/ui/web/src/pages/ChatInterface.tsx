import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  Paper,
  TextField,
  IconButton,
  Button,
  Typography,
  Avatar,
  Chip,
  CircularProgress,
} from '@mui/material';
import {
  Send as SendIcon,
  SmartToy as BotIcon,
  Person as PersonIcon,
} from '@mui/icons-material';
import { useMutation } from '@tanstack/react-query';
import { chatAPI } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

interface Message {
  id: string;
  content: string;
  sender: 'user' | 'assistant';
  timestamp: Date;
  route?: string;
  intent?: string;
  confidence?: number;
  recommendations?: string[];
  structured_data?: any;
}

const ChatInterface: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const MESSAGES_PER_PAGE = 50; // Load 50 messages at a time
  const [allMessages, setAllMessages] = useState<Message[]>([
    {
      id: '1',
      content: '您好！我是您的多智能体智能仓库助手。今天有什么可以帮您？',
      sender: 'assistant',
      timestamp: new Date(),
    },
  ]);
  const [displayedMessages, setDisplayedMessages] = useState<Message[]>([]);
  const [messagesToShow, setMessagesToShow] = useState(MESSAGES_PER_PAGE);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Update displayed messages when allMessages or messagesToShow changes
  useEffect(() => {
    const startIndex = Math.max(0, allMessages.length - messagesToShow);
    setDisplayedMessages(allMessages.slice(startIndex));
  }, [allMessages, messagesToShow]);

  useEffect(() => {
    scrollToBottom();
  }, [displayedMessages]);

  const loadMoreMessages = () => {
    setMessagesToShow(prev => Math.min(prev + MESSAGES_PER_PAGE, allMessages.length));
  };

  const hasMoreMessages = messagesToShow < allMessages.length;

  const getRouteLabel = (route?: string) => {
    const labels: Record<string, string> = {
      equipment: '设备智能体',
      operations: '运营智能体',
      safety: '安全智能体',
      general: '通用助手',
    };
    return route ? (labels[route] || route) : '助手';
  };

  const sendMessageMutation = useMutation({
    mutationFn: chatAPI.sendMessage,
    onSuccess: (response) => {
      const assistantMessage: Message = {
        id: Date.now().toString(),
        content: response.reply,
        sender: 'assistant',
        timestamp: new Date(),
        route: response.route,
        intent: response.intent,
        confidence: response.confidence,
        recommendations: response.recommendations,
        structured_data: response.structured_data,
      };
      setAllMessages(prev => [...prev, assistantMessage]);
      setIsLoading(false);
    },
    onError: (error: any) => {
      console.error('Error sending message:', error);
      let errorContent = '抱歉，发生错误，请重试。';
      
      if (error?.response?.status === 401) {
        errorContent = '身份验证失败，请重新登录。';
      } else if (error?.response?.status === 403) {
        errorContent = '访问被拒绝，请检查您的权限。';
      } else if (error?.code === 'ECONNABORTED') {
        errorContent = '请求超时，请重试。';
      } else if (error?.response?.data?.detail) {
        errorContent = `错误：${error.response.data.detail}`;
      }
      
      const errorMessage: Message = {
        id: Date.now().toString(),
        content: errorContent,
        sender: 'assistant',
        timestamp: new Date(),
      };
      setAllMessages(prev => [...prev, errorMessage]);
      setIsLoading(false);
    },
  });

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;
    
    if (!isAuthenticated) {
      const errorMessage: Message = {
        id: Date.now().toString(),
        content: '请登录后使用聊天界面。',
        sender: 'assistant',
        timestamp: new Date(),
      };
      setAllMessages(prev => [...prev, errorMessage]);
      return;
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      content: inputValue,
      sender: 'user',
      timestamp: new Date(),
    };

    setAllMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      await sendMessageMutation.mutateAsync({
        message: inputValue,
        session_id: 'web_session',
        context: { user_id: 'web_user' },
      });
    } catch (error) {
      console.error('Failed to send message:', error);
    }
  };

  const handleKeyPress = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <Box sx={{ height: 'calc(100vh - 120px)', display: 'flex', flexDirection: 'column' }}>
      <Typography variant="h4" gutterBottom>
        聊天助手
      </Typography>
      
      <Paper
        elevation={3}
        sx={{
          flexGrow: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Messages Area */}
        <Box
          sx={{
            flexGrow: 1,
            overflow: 'auto',
            p: 2,
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
          }}
        >
          {hasMoreMessages && (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
              <Button
                onClick={loadMoreMessages}
                color="primary"
                variant="outlined"
                size="small"
              >
                加载更多消息（还有 {allMessages.length - messagesToShow} 条较早消息）
              </Button>
            </Box>
          )}
          {displayedMessages.map((message) => (
            <Box
              key={message.id}
              sx={{
                display: 'flex',
                justifyContent: message.sender === 'user' ? 'flex-end' : 'flex-start',
                alignItems: 'flex-start',
                gap: 1,
              }}
            >
              {message.sender === 'assistant' && (
                <Avatar sx={{ bgcolor: 'primary.main' }}>
                  <BotIcon />
                </Avatar>
              )}
              
              <Box
                sx={{
                  maxWidth: '70%',
                  p: 2,
                  borderRadius: 2,
                  bgcolor: message.sender === 'user' ? 'primary.main' : 'grey.100',
                  color: message.sender === 'user' ? 'white' : 'text.primary',
                }}
              >
                <Typography variant="body1">{message.content}</Typography>
                
                {message.confidence && (
                  <Box sx={{ mt: 1, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                    <Chip
                      label={`${getRouteLabel(message.route)}（${Math.round(message.confidence * 100)}%）`}
                      size="small"
                      color="secondary"
                    />
                    {message.intent && (
                      <Chip
                        label={message.intent}
                        size="small"
                        variant="outlined"
                      />
                    )}
                  </Box>
                )}
                
                {message.structured_data && message.structured_data.items && message.structured_data.items.length > 0 && (
                  <Box sx={{ mt: 2 }}>
                    <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                      设备详情：
                    </Typography>
                    {message.structured_data.items.map((item: any, index: number) => (
                      <Box key={index} sx={{ 
                        p: 2, 
                        border: 1, 
                        borderColor: 'divider', 
                        borderRadius: 1, 
                        mb: 1,
                        bgcolor: 'background.paper'
                      }}>
                        <Typography variant="subtitle1" fontWeight="bold">
                          {item.name} ({item.sku})
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          <strong>库存量：</strong> {item.quantity} 件
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          <strong>位置：</strong> {item.location}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          <strong>补货点：</strong> {item.reorder_point} 件
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          <strong>状态：</strong> {item.quantity <= item.reorder_point ? '库存不足' : '库存充足'}
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                )}
                
                {message.recommendations && message.recommendations.length > 0 && (
                  <Box sx={{ mt: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      建议：
                    </Typography>
                    {message.recommendations.map((rec, index) => (
                      <Typography key={index} variant="caption" display="block">
                        • {rec}
                      </Typography>
                    ))}
                  </Box>
                )}
              </Box>
              
              {message.sender === 'user' && (
                <Avatar sx={{ bgcolor: 'secondary.main' }}>
                  <PersonIcon />
                </Avatar>
              )}
            </Box>
          ))}
          
          {isLoading && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Avatar sx={{ bgcolor: 'primary.main' }}>
                <BotIcon />
              </Avatar>
              <Box sx={{ p: 2, borderRadius: 2, bgcolor: 'grey.100' }}>
                <CircularProgress size={20} />
                <Typography variant="body2" sx={{ ml: 1, display: 'inline' }}>
                  正在思考...
                </Typography>
              </Box>
            </Box>
          )}
          
          <div ref={messagesEndRef} />
        </Box>

        {/* Input Area */}
        <Box
          sx={{
            p: 2,
            borderTop: 1,
            borderColor: 'divider',
            display: 'flex',
            gap: 1,
            alignItems: 'flex-end',
          }}
        >
          <TextField
            fullWidth
            multiline
            maxRows={4}
            placeholder="您可以询问设备、运营、安全或任何仓库相关问题..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={isLoading}
            variant="outlined"
            size="small"
          />
          <IconButton
            aria-label="发送消息"
            color="primary"
            onClick={handleSendMessage}
            disabled={!inputValue.trim() || isLoading}
            sx={{ alignSelf: 'flex-end' }}
          >
            <SendIcon />
          </IconButton>
        </Box>
      </Paper>
    </Box>
  );
};

export default ChatInterface;
