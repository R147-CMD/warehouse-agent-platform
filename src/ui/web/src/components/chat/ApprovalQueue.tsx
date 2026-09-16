import React, { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  IconButton,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  Cancel as CancelIcon,
  CheckCircle as CheckCircleIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import { approvalAPI } from '../../services/api';

interface ApprovalQueueProps {
  enabled: boolean;
  busyApprovalIds: ReadonlySet<string>;
  onDecision: (
    approvalId: string,
    decision: 'approve' | 'reject',
    action: string,
  ) => Promise<void>;
}

const formatDateTime = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? '未知'
    : date.toLocaleString('zh-CN', { hour12: false });
};

const ApprovalQueue: React.FC<ApprovalQueueProps> = ({
  enabled,
  busyApprovalIds,
  onDecision,
}) => {
  const [localBusyIds, setLocalBusyIds] = useState<Set<string>>(() => new Set());
  const {
    data: approvals = [],
    error,
    isLoading,
    isFetching,
    refetch,
  } = useQuery({
    queryKey: ['pending-approvals'],
    queryFn: approvalAPI.listPending,
    enabled,
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 15000,
  });

  const handleDecision = async (
    approvalId: string,
    decision: 'approve' | 'reject',
    action: string,
  ) => {
    if (localBusyIds.has(approvalId) || busyApprovalIds.has(approvalId)) return;

    setLocalBusyIds(prev => new Set(prev).add(approvalId));
    try {
      await onDecision(approvalId, decision, action);
      await refetch();
    } finally {
      setLocalBusyIds(prev => {
        const next = new Set(prev);
        next.delete(approvalId);
        return next;
      });
    }
  };

  if (!enabled) return null;

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
          {approvals.length > 0 ? `${approvals.length} 项待处理` : '实时审批队列'}
        </Typography>
        <Tooltip title="刷新待审批列表">
          <span>
            <IconButton
              aria-label="刷新待审批列表"
              size="small"
              onClick={() => void refetch()}
              disabled={isFetching}
              sx={{ color: 'primary.main' }}
            >
              {isFetching ? <CircularProgress size={16} /> : <RefreshIcon fontSize="small" />}
            </IconButton>
          </span>
        </Tooltip>
      </Box>

      {isLoading && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 1 }}>
          <CircularProgress size={18} />
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            正在加载待审批操作…
          </Typography>
        </Box>
      )}

      {!isLoading && error && (
        <Alert severity="error" sx={{ py: 0.5 }}>
          暂时无法加载待审批操作。
        </Alert>
      )}

      {!isLoading && !error && approvals.length === 0 && (
        <Typography variant="body2" sx={{ color: 'text.secondary', fontStyle: 'italic', py: 1 }}>
          暂无待审批操作
        </Typography>
      )}

      {!isLoading && !error && approvals.length > 0 && (
        <Box sx={{ maxHeight: 260, overflowY: 'auto' }}>
          {approvals.map((approval) => {
            const busy = localBusyIds.has(approval.approval_id) || busyApprovalIds.has(approval.approval_id);
            return (
              <Card
                key={approval.approval_id}
                variant="outlined"
                sx={{ mb: 1, backgroundColor: 'background.default', borderColor: 'divider' }}
              >
                <CardContent sx={{ p: 1.25, '&:last-child': { pb: 1.25 } }}>
                  <Typography variant="body2" sx={{ color: 'text.primary', fontWeight: 500 }}>
                    {approval.action || '未命名操作'}
                  </Typography>
                  <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                    工具：{approval.tool_name || '未知'}
                  </Typography>
                  <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                    请求人：{approval.requester_username || '未知'}
                  </Typography>
                  <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 1 }}>
                    到期：{formatDateTime(approval.expires_at)}
                  </Typography>
                  <Box sx={{ display: 'flex', gap: 0.75 }}>
                    <Button
                      variant="contained"
                      size="small"
                      startIcon={busy ? <CircularProgress size={14} color="inherit" /> : <CheckCircleIcon />}
                      onClick={() => void handleDecision(approval.approval_id, 'approve', approval.action)}
                      disabled={busy}
                    >
                      批准执行
                    </Button>
                    <Button
                      variant="outlined"
                      color="error"
                      size="small"
                      startIcon={<CancelIcon />}
                      onClick={() => void handleDecision(approval.approval_id, 'reject', approval.action)}
                      disabled={busy}
                    >
                      拒绝
                    </Button>
                  </Box>
                </CardContent>
              </Card>
            );
          })}
        </Box>
      )}
    </Box>
  );
};

export default ApprovalQueue;
