import React from 'react';
import { Chip } from '@mui/material';
import { AgentRunStatus } from '../../services/api';

const statusMap: Record<AgentRunStatus, { label: string; color: 'default' | 'primary' | 'success' | 'warning' | 'error' | 'info' }> = {
  queued: { label: '排队中', color: 'default' },
  running: { label: '执行中', color: 'primary' },
  waiting_approval: { label: '待审批', color: 'warning' },
  completed: { label: '已完成', color: 'success' },
  failed: { label: '失败', color: 'error' },
  cancel_requested: { label: '取消中', color: 'info' },
  cancelled: { label: '已取消', color: 'default' },
};

interface RunStatusBadgeProps {
  status: AgentRunStatus;
}

const RunStatusBadge: React.FC<RunStatusBadgeProps> = ({ status }) => {
  const item = statusMap[status] || statusMap.queued;
  return <Chip size="small" label={item.label} color={item.color} />;
};

export default RunStatusBadge;
