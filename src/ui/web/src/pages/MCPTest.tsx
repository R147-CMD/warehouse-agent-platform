import React from 'react';
import { Box, Typography, Container } from '@mui/material';
import EnhancedMCPTestingPanel from '../components/EnhancedMCPTestingPanel';

const MCPTestPage: React.FC = () => {
  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          MCP 测试仪表板
        </Typography>
        <Typography variant="body1" color="text.secondary">
          测试并探索模型上下文协议（MCP）框架集成
        </Typography>
      </Box>
      
      <EnhancedMCPTestingPanel />
    </Container>
  );
};

export default MCPTestPage;
