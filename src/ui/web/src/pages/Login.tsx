import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Alert,
  CircularProgress,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

interface LoginForm {
  username: string;
  password: string;
}

const Login: React.FC = () => {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [formData, setFormData] = useState<LoginForm>({
    username: '',
    password: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await login(formData.username, formData.password);
      navigate('/');
    } catch {
      setError('登录失败，请检查用户名和密码，或稍后重试。');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        backgroundColor: '#f5f5f5',
      }}
    >
      <Card sx={{ maxWidth: 400, width: '100%', mx: 2 }}>
        <CardContent sx={{ p: 4 }}>
          <Typography variant="h4" component="h1" gutterBottom align="center">
            仓智智能仓储运营平台
          </Typography>
          <Typography variant="body2" color="text.secondary" align="center" sx={{ mb: 3 }}>
            登录后访问智能仓储运营与协同管理平台
          </Typography>

          {error && (
            <Alert 
              severity="error" 
              sx={{ 
                mb: 2,
                backgroundColor: '#161B22',
                border: '1px solid #F85149',
                '& .MuiAlert-icon': {
                  color: '#F85149',
                },
                '& .MuiAlert-message': {
                  color: '#E6EDF3',
                },
              }}
            >
              {error}
            </Alert>
          )}

          <form onSubmit={handleSubmit}>
            <TextField
              fullWidth
              label="用户名"
              name="username"
              value={formData.username}
              onChange={handleInputChange}
              margin="normal"
              required
              autoComplete="username"
              autoFocus
            />
            <TextField
              fullWidth
              label="密码"
              name="password"
              type="password"
              value={formData.password}
              onChange={handleInputChange}
              margin="normal"
              required
              autoComplete="current-password"
            />
            <Button
              type="submit"
              fullWidth
              variant="contained"
              disabled={loading}
              sx={{ 
                mt: 3, 
                mb: 2,
                backgroundColor: '#76B900',
                color: '#000000',
                fontWeight: 500,
                textTransform: 'none',
                py: 1.5,
                fontSize: '0.9375rem',
                '&:hover': {
                  backgroundColor: '#8FD600',
                },
                '&:disabled': {
                  backgroundColor: '#21262D',
                  color: '#8B949E',
                },
              }}
            >
              {loading ? <CircularProgress size={24} sx={{ color: '#8B949E' }} /> : '登录'}
            </Button>
          </form>

          <Box 
            sx={{ 
              mt: 2, 
              p: 2, 
              backgroundColor: '#0D1117', 
              borderRadius: 1,
              border: '1px solid #30363D',
            }}
          >
            <Typography 
              variant="body2" 
              sx={{
                color: '#8B949E',
                fontSize: '0.875rem',
                mb: 0.5,
              }}
            >
              <strong style={{ color: '#E6EDF3' }}>演示账号：</strong>
            </Typography>
            <Typography 
              variant="body2" 
              sx={{
                color: '#8B949E',
                fontSize: '0.875rem',
              }}
            >
              用户名：admin
            </Typography>
            <Typography 
              variant="body2" 
              sx={{
                color: '#8B949E',
                fontSize: '0.875rem',
              }}
            >
              密码：由 DEFAULT_ADMIN_PASSWORD 环境变量设置
            </Typography>
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
};

export default Login;
