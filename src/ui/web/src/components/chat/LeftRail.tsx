import React, { useState } from 'react';
import {
  Box,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Typography,
  Divider,
  Chip,
  Tabs,
  Tab,
  Button,
} from '@mui/material';
import {
  Inventory as InventoryIcon,
  Assignment as AssignmentIcon,
  Security as SecurityIcon,
  History as HistoryIcon,
  TrendingUp as TrendingUpIcon,
  Warning as WarningIcon,
  AddComment as AddCommentIcon,
} from '@mui/icons-material';
import DemoScript from './DemoScript';

interface LeftRailProps {
  onScenarioSelect: (scenario: string) => void;
  onNewConversation: () => void;
  approvalQueue?: React.ReactNode;
  recentTasks: Array<{
    id: string;
    title: string;
    status: 'pending' | 'completed' | 'failed';
    timestamp: Date;
  }>;
}

const LeftRail: React.FC<LeftRailProps> = ({
  onScenarioSelect,
  onNewConversation,
  approvalQueue,
  recentTasks,
}) => {
  const [activeTab, setActiveTab] = useState(0);
  const scenarios = [
    { id: 'create_pick_wave', label: '创建拣货波次', icon: <InventoryIcon /> },
    { id: 'dispatch_forklift', label: '调度叉车', icon: <AssignmentIcon /> },
    { id: 'log_incident', label: '记录事故', icon: <SecurityIcon /> },
    { id: 'check_assets', label: '检查设备资产', icon: <TrendingUpIcon /> },
    { id: 'safety_check', label: '安全检查', icon: <WarningIcon /> },
  ];

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return '#76B900';
      case 'pending': return '#ff9800';
      case 'failed': return '#f44336';
      default: return '#666666';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'completed': return '已完成';
      case 'pending': return '待处理';
      case 'failed': return '失败';
      default: return status;
    }
  };

  return (
    <Box
      sx={{
        width: 300,
        height: '100%',
        backgroundColor: 'background.paper',
        borderRight: '1px solid',
        borderColor: 'divider',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Box sx={{ p: 2, pb: 1 }}>
        <Button
          fullWidth
          variant="outlined"
          startIcon={<AddCommentIcon />}
          onClick={onNewConversation}
          aria-label="新建会话"
          sx={{
            justifyContent: 'flex-start',
            color: 'primary.main',
            borderColor: 'primary.main',
            '&:hover': {
              borderColor: 'primary.light',
              backgroundColor: 'rgba(118, 185, 0, 0.08)',
            },
          }}
        >
          新建会话
        </Button>
      </Box>

      {approvalQueue && (
        <Box sx={{ px: 2, pb: 1.5, borderBottom: '1px solid', borderColor: 'divider' }}>
          <Typography variant="h6" sx={{ color: 'text.primary', mb: 1, fontSize: '14px', fontWeight: 500 }}>
            待审批
          </Typography>
          {approvalQueue}
        </Box>
      )}

      {/* Tabs */}
      <Box sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Tabs
          value={activeTab}
          onChange={(_, newValue) => setActiveTab(newValue)}
          sx={{
            '& .MuiTab-root': {
              color: 'text.secondary',
              fontSize: '12px',
              minHeight: '40px',
              '&.Mui-selected': {
                color: 'primary.main',
              },
            },
          }}
        >
          <Tab label="快捷操作" />
          <Tab label="演示脚本" />
        </Tabs>
      </Box>

      {/* Tab Content */}
      <Box sx={{ flex: 1, overflow: 'hidden' }}>
        {activeTab === 0 && (
          <Box sx={{ p: 2, height: '100%', overflow: 'auto' }}>
            <Typography variant="h6" sx={{ color: 'text.primary', mb: 2, fontSize: '14px', fontWeight: 500 }}>
              快捷操作
            </Typography>
            <List dense>
              {scenarios.map((scenario) => (
                <ListItem key={scenario.id} disablePadding>
                  <ListItemButton
                    onClick={() => onScenarioSelect(scenario.id)}
                    sx={{
                      borderRadius: 1,
                      mb: 0.5,
                    }}
                  >
                    <ListItemIcon sx={{ color: 'primary.main', minWidth: 32 }}>
                      {scenario.icon}
                    </ListItemIcon>
                    <ListItemText
                      primary={scenario.label}
                      primaryTypographyProps={{
                        fontSize: '12px',
                        color: 'text.primary',
                      }}
                    />
                  </ListItemButton>
                </ListItem>
              ))}
            </List>

            <Divider sx={{ my: 2 }} />

            <Typography variant="h6" sx={{ color: 'text.primary', mb: 2, fontSize: '14px', fontWeight: 500 }}>
              最近任务
            </Typography>
            <List dense>
              {recentTasks.length === 0 ? (
                <Typography variant="body2" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>
                  暂无最近任务
                </Typography>
              ) : (
                recentTasks.map((task) => (
                  <ListItem key={task.id} disablePadding>
                    <ListItemButton
                      sx={{
                        borderRadius: 1,
                        mb: 0.5,
                      }}
                    >
                      <ListItemIcon sx={{ minWidth: 32 }}>
                        <HistoryIcon sx={{ color: 'text.secondary', fontSize: '16px' }} />
                      </ListItemIcon>
                      <ListItemText
                        primary={task.title}
                        secondary={
                          <Typography variant="caption" sx={{ color: 'text.secondary', display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
                            <Chip
                              label={getStatusLabel(task.status)}
                              size="small"
                              sx={{
                                backgroundColor: getStatusColor(task.status),
                                color: '#ffffff',
                                fontSize: '10px',
                                height: '16px',
                              }}
                            />
                            {task.timestamp.toLocaleTimeString('zh-CN', { hour12: false })}
                          </Typography>
                        }
                        primaryTypographyProps={{
                          fontSize: '12px',
                          color: 'text.primary',
                        }}
                      />
                    </ListItemButton>
                  </ListItem>
                ))
              )}
            </List>
          </Box>
        )}

        {activeTab === 1 && (
          <DemoScript onScenarioSelect={onScenarioSelect} />
        )}
      </Box>
    </Box>
  );
};

export default LeftRail;
