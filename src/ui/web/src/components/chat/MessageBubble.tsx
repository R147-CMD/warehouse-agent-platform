import React from 'react';
import {
  Box,
  Typography,
  Avatar,
  Chip,
  Card,
  CardContent,
  Button,
  CircularProgress,
  LinearProgress,
  Tooltip,
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Cancel as CancelIcon,
  Info as InfoIcon,
  Warning as WarningIcon,
  Error as ErrorIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
} from '@mui/icons-material';
import { Link as RouterLink } from 'react-router-dom';
import ReasoningChainVisualization from './ReasoningChainVisualization';
import { PendingApproval, ReasoningChain, ReasoningStep } from '../../services/api';

interface MessageBubbleProps {
  message: {
    id: string;
    type: 'answer' | 'clarifying_question' | 'proposed_action' | 'action_result' | 'evidence' | 'notice' | 'warning' | 'error';
    content: string;
    sender: 'user' | 'assistant';
    timestamp: Date;
    route?: string;
    run_id?: string | null;
    confidence?: number;
    structured_data?: any;
    proposals?: PendingApproval[];
    clarifying?: {
      text: string;
      options: string[];
    };
    evidence?: Array<{
      type: 'sql' | 'doc';
      table?: string;
      rows?: number;
      lat_ms?: number;
      id?: string;
      score?: number;
    }>;
    reasoning_chain?: ReasoningChain;
    reasoning_steps?: ReasoningStep[];
  };
  canApprove: boolean;
  busyApprovalIds: ReadonlySet<string>;
  onActionApprove: (approvalId: string, action: string) => Promise<void>;
  onActionReject: (approvalId: string, action: string) => Promise<void>;
  onQuickReply: (option: string) => void;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  canApprove,
  busyApprovalIds,
  onActionApprove,
  onActionReject,
  onQuickReply,
}) => {
  const [expanded, setExpanded] = React.useState(false);
  const [imageError, setImageError] = React.useState(false);

  const formatDateTime = (value: string) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? '未知'
      : date.toLocaleString('zh-CN', { hour12: false });
  };

  const getApprovalStatusLabel = (status: PendingApproval['status']) => {
    const labels: Record<PendingApproval['status'], string> = {
      pending: '待审批',
      approved: '已批准',
      executing: '执行中',
      executed: '已执行',
      rejected: '已拒绝',
      expired: '已过期',
      failed: '执行失败',
    };
    return labels[status];
  };

  const getAgentIcon = (route?: string) => {
    switch (route) {
      case 'equipment': return '🔧';
      case 'operations': return '📋';
      case 'safety': return '🛡️';
      default: return '🤖';
    }
  };

  const getAgentColor = (route?: string) => {
    switch (route) {
      case 'equipment': return '#76B900';
      case 'operations': return '#2196F3';
      case 'safety': return '#FF9800';
      default: return '#9C27B0';
    }
  };

  const getAgentLabel = (route?: string) => {
    switch (route) {
      case 'equipment': return '设备智能体';
      case 'operations': return '运营智能体';
      case 'safety': return '安全智能体';
      case 'system': return '系统';
      case 'general': return '助手';
      default: return route || '助手';
    }
  };

  const getConfidenceColor = (confidence?: number) => {
    if (!confidence) return '#666666';
    if (confidence >= 0.8) return '#76B900';
    if (confidence >= 0.6) return '#FF9800';
    return '#f44336';
  };

  const getConfidenceIcon = (confidence?: number) => {
    if (!confidence) return null;
    if (confidence >= 0.8) return '🟢';
    if (confidence >= 0.6) return '🟡';
    return '🔴';
  };

  const renderStructuredData = () => {
    if (!message.structured_data) return null;

    // Handle the actual API response structure
    if (message.structured_data.response_type === 'equipment_info') {
      return (
        <Card sx={{ mt: 1, backgroundColor: 'background.paper', border: '1px solid', borderColor: 'divider', boxShadow: 1 }}>
          <CardContent>
            <Typography variant="h6" sx={{ color: 'text.primary', mb: 1, fontWeight: 500 }}>
              设备信息
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
              {typeof message.structured_data.natural_language === 'string' 
                ? message.structured_data.natural_language 
                : '暂无说明'}
            </Typography>
            
            {message.structured_data.data && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" sx={{ color: 'text.primary', mb: 1, fontWeight: 500 }}>
                  数据摘要：
                </Typography>
                <Box sx={{ backgroundColor: 'background.default', p: 1, borderRadius: 1, fontFamily: 'monospace', fontSize: '10px', border: '1px solid', borderColor: 'divider' }}>
                  <pre style={{ color: 'text.primary', margin: 0, whiteSpace: 'pre-wrap' }}>
                    {JSON.stringify(message.structured_data.data, null, 2)}
                  </pre>
                </Box>
              </Box>
            )}

            {message.structured_data.recommendations && message.structured_data.recommendations.length > 0 && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" sx={{ color: 'text.primary', mb: 1, fontWeight: 500 }}>
                  建议：
                </Typography>
                {message.structured_data.recommendations.map((rec: string, index: number) => (
                  <Typography key={index} variant="caption" sx={{ color: 'primary.main', display: 'block' }}>
                    • {rec}
                  </Typography>
                ))}
              </Box>
            )}

            {message.structured_data.confidence && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" sx={{ color: 'text.primary', mb: 1, fontWeight: 500 }}>
                  置信度：{(message.structured_data.confidence * 100).toFixed(1)}%
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={message.structured_data.confidence * 100}
                  sx={{
                    height: 4,
                    borderRadius: 2,
                    backgroundColor: 'grey.700',
                    '& .MuiLinearProgress-bar': {
                      backgroundColor: message.structured_data.confidence >= 0.8 ? 'primary.main' : 'warning.main',
                    },
                  }}
                />
              </Box>
            )}
          </CardContent>
        </Card>
      );
    }

    // Handle table structure (legacy)
    if (message.structured_data.type === 'table') {
      return (
        <Card sx={{ mt: 1, backgroundColor: 'background.paper', border: '1px solid', borderColor: 'divider', boxShadow: 1 }}>
          <CardContent>
            <Typography variant="h6" sx={{ color: 'text.primary', mb: 1, fontWeight: 500 }}>
              {message.structured_data.title}
            </Typography>
            <Box sx={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', color: 'inherit' }}>
                <thead>
                  <tr>
                    {message.structured_data.headers.map((header: string, index: number) => (
                      <th key={index} style={{ padding: '8px', textAlign: 'left', borderBottom: '1px solid', borderColor: 'divider', fontWeight: 500, color: 'text.secondary' }}>
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {message.structured_data.rows.map((row: any[], rowIndex: number) => (
                    <tr key={rowIndex}>
                      {row.map((cell: any, cellIndex: number) => (
                        <td key={cellIndex} style={{ padding: '8px', borderBottom: '1px solid', borderColor: 'divider', color: 'text.primary' }}>
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Box>
          </CardContent>
        </Card>
      );
    }

    // Fallback: render as JSON if it's an object
    if (typeof message.structured_data === 'object') {
      return (
        <Card sx={{ mt: 1, backgroundColor: 'background.paper', border: '1px solid', borderColor: 'divider', boxShadow: 1 }}>
          <CardContent>
            <Typography variant="h6" sx={{ color: 'text.primary', mb: 1, fontWeight: 500 }}>
              结构化数据
            </Typography>
            <Box sx={{ backgroundColor: 'background.default', p: 1, borderRadius: 1, fontFamily: 'monospace', fontSize: '10px', border: '1px solid', borderColor: 'divider' }}>
              <pre style={{ color: 'inherit', margin: 0, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(message.structured_data, null, 2)}
              </pre>
            </Box>
          </CardContent>
        </Card>
      );
    }

    return null;
  };

  const renderProposedActions = () => {
    if (!message.proposals || message.proposals.length === 0) return null;

    return (
      <Box sx={{ mt: 1 }}>
        {message.proposals.map((proposal) => {
          const busy = busyApprovalIds.has(proposal.approval_id);
          return (
            <Card key={proposal.approval_id} sx={{ mt: 1, backgroundColor: 'background.paper', border: '1px solid', borderColor: 'divider', boxShadow: 1 }}>
              <CardContent>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                  <Typography variant="h6" sx={{ color: 'text.primary', fontWeight: 500 }}>
                    操作：{proposal.action || '未命名操作'}
                  </Typography>
                  <Chip
                    label={getApprovalStatusLabel(proposal.status)}
                    size="small"
                    sx={{
                      backgroundColor: proposal.status === 'pending' ? 'warning.main' : 'grey.700',
                      color: '#ffffff',
                    }}
                  />
                </Box>

              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1 }}>
                工具：{proposal.tool_name || '未知'}
              </Typography>
              <Box sx={{ mb: 1 }}>
                <Typography variant="body2" sx={{ color: 'text.primary', fontWeight: 500 }}>
                  参数：
                </Typography>
                <Box sx={{ mt: 0.5, p: 1, borderRadius: 1, backgroundColor: 'background.default', overflowX: 'auto' }}>
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: '12px' }}>
                    {JSON.stringify(proposal.arguments, null, 2)}
                  </pre>
                </Box>
              </Box>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 0.5 }}>
                风险等级：{proposal.risk_level === 'high' ? '高' : '未知'}
              </Typography>
              {proposal.risk_reasons.length > 0 && (
                <Typography variant="body2" sx={{ color: 'text.secondary', mb: 0.5 }}>
                  风险原因：{proposal.risk_reasons.join('；')}
                </Typography>
              )}
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 0.5 }}>
                请求人：{proposal.requester_username || '未知'}
              </Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1.5 }}>
                到期时间：{formatDateTime(proposal.expires_at)}
              </Typography>

              {canApprove && proposal.status === 'pending' && (
                <Box sx={{ display: 'flex', gap: 1 }}>
                <Button
                  variant="contained"
                  size="small"
                  startIcon={busy ? <CircularProgress size={14} color="inherit" /> : <CheckCircleIcon />}
                  onClick={() => void onActionApprove(proposal.approval_id, proposal.action)}
                  disabled={busy}
                  sx={{
                    backgroundColor: 'primary.main',
                    color: 'primary.contrastText',
                    '&:hover': { backgroundColor: 'primary.light' },
                  }}
                >
                  批准执行
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<CancelIcon />}
                  onClick={() => void onActionReject(proposal.approval_id, proposal.action)}
                  disabled={busy}
                  sx={{
                    borderColor: 'error.main',
                    color: 'error.main',
                    '&:hover': { borderColor: 'error.light', backgroundColor: 'rgba(248, 81, 73, 0.1)' },
                  }}
                >
                  拒绝
                </Button>
                </Box>
              )}
              {!canApprove && proposal.status === 'pending' && (
                <Typography variant="body2" sx={{ color: 'warning.main', fontWeight: 500 }}>
                  等待经理审批
                </Typography>
              )}
              </CardContent>
            </Card>
          );
        })}
      </Box>
    );
  };

  const renderClarifyingQuestion = () => {
    if (!message.clarifying) return null;

    return (
      <Card sx={{ mt: 1, backgroundColor: 'background.paper', border: '1px solid', borderColor: 'divider', boxShadow: 1 }}>
        <CardContent>
          <Typography variant="h6" sx={{ color: 'text.primary', mb: 1, fontWeight: 500 }}>
            {message.clarifying.text}
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {message.clarifying.options.map((option, index) => (
              <Chip
                key={index}
                label={option}
                clickable
                onClick={() => onQuickReply(option)}
                sx={{
                  backgroundColor: 'grey.700',
                  color: 'text.primary',
                  '&:hover': { backgroundColor: 'primary.main', color: 'primary.contrastText' },
                }}
              />
            ))}
          </Box>
        </CardContent>
      </Card>
    );
  };

  const renderNotice = () => {
    if (message.type !== 'notice' && message.type !== 'warning' && message.type !== 'error') return null;

    const getNoticeIcon = () => {
      switch (message.type) {
        case 'warning': return <WarningIcon sx={{ color: '#FF9800' }} />;
        case 'error': return <ErrorIcon sx={{ color: '#f44336' }} />;
        default: return <InfoIcon sx={{ color: '#2196F3' }} />;
      }
    };

    const getNoticeColor = () => {
      switch (message.type) {
        case 'warning': return '#FF9800';
        case 'error': return '#f44336';
        default: return '#2196F3';
      }
    };

    return (
      <Card sx={{ mt: 1, backgroundColor: 'background.paper', border: `1px solid ${getNoticeColor()}`, boxShadow: 1 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {getNoticeIcon()}
            <Typography variant="body1" sx={{ color: 'text.primary' }}>
              {message.content}
            </Typography>
          </Box>
        </CardContent>
      </Card>
    );
  };

  const isUser = message.sender === 'user';

  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        mb: 2,
        px: 2,
      }}
    >
      <Box
        sx={{
          maxWidth: '70%',
          display: 'flex',
          flexDirection: isUser ? 'row-reverse' : 'row',
          alignItems: 'flex-start',
          gap: 1,
        }}
      >
        {/* Avatar */}
        {!isUser && (
          <Avatar
            src={imageError ? undefined : "/assistant-avatar.png"}
            alt="助手头像"
            sx={{
              width: 32,
              height: 32,
              border: '2px solid',
              borderColor: 'primary.main',
              backgroundColor: imageError ? getAgentColor(message.route) : 'transparent',
              '& .MuiAvatar-img': {
                objectFit: 'cover',
              },
            }}
            onError={() => {
              // Fallback to emoji icon if image fails to load
              setImageError(true);
            }}
          >
            {imageError ? getAgentIcon(message.route) : null}
          </Avatar>
        )}

        {/* Message Content */}
        <Box
          sx={{
            backgroundColor: isUser ? 'primary.main' : 'background.paper',
            color: isUser ? 'primary.contrastText' : 'text.primary',
            borderRadius: 2,
            p: 2,
            border: isUser ? 'none' : '1px solid',
            borderColor: isUser ? 'transparent' : 'divider',
            minWidth: 200,
            boxShadow: isUser ? 'none' : 1,
          }}
        >
          {/* Message Header */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="body2" sx={{ color: isUser ? 'primary.contrastText' : 'text.secondary', fontWeight: 500 }}>
              {isUser ? '您' : getAgentLabel(message.route)}
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {message.confidence && (
                <Tooltip title={`置信度：${(message.confidence * 100).toFixed(1)}%`}>
                  <Chip
                    label={`${getConfidenceIcon(message.confidence)} ${(message.confidence * 100).toFixed(0)}%`}
                    size="small"
                    sx={{
                      backgroundColor: getConfidenceColor(message.confidence),
                      color: '#ffffff',
                      fontSize: '10px',
                    }}
                  />
                </Tooltip>
              )}
              <Typography variant="caption" sx={{ color: isUser ? 'rgba(255,255,255,0.8)' : 'text.secondary' }}>
                {message.timestamp.toLocaleTimeString()}
              </Typography>
            </Box>
          </Box>

          {/* Message Content */}
          <Typography variant="body1" sx={{ color: isUser ? 'primary.contrastText' : 'text.primary', mb: 1 }}>
            {message.content}
          </Typography>

          {!isUser && message.run_id && (
            <Button
              component={RouterLink}
              to={`/runs?run_id=${encodeURIComponent(message.run_id)}`}
              size="small"
              sx={{
                mt: 0.5,
                mb: 1,
                color: 'primary.main',
                px: 0,
                justifyContent: 'flex-start',
              }}
            >
              查看任务记录
            </Button>
          )}

          {/* Confidence Bar */}
          {message.confidence && (
            <Box sx={{ mb: 1 }}>
              <LinearProgress
                variant="determinate"
                value={message.confidence * 100}
                sx={{
                  height: 4,
                  borderRadius: 2,
                  backgroundColor: isUser ? 'rgba(255,255,255,0.3)' : '#e0e0e0',
                  '& .MuiLinearProgress-bar': {
                    backgroundColor: getConfidenceColor(message.confidence),
                  },
                }}
              />
            </Box>
          )}

          {/* Reasoning Chain - shown BEFORE structured data */}
          {(message.reasoning_chain || message.reasoning_steps) && (
            <Box sx={{ mt: 1, mb: 1 }}>
              <ReasoningChainVisualization
                reasoningChain={message.reasoning_chain}
                reasoningSteps={message.reasoning_steps}
                compact={true}
              />
            </Box>
          )}

          {/* Structured Data - shown AFTER reasoning chain */}
          {renderStructuredData()}

          {/* Proposed Actions */}
          {renderProposedActions()}

          {/* Clarifying Question */}
          {renderClarifyingQuestion()}

          {/* Notice/Warning/Error */}
          {renderNotice()}

          {/* Evidence Toggle */}
          {message.evidence && message.evidence.length > 0 && (
            <Box sx={{ mt: 1 }}>
              <Button
                size="small"
                onClick={() => setExpanded(!expanded)}
                endIcon={expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                sx={{ color: 'primary.main' }}
              >
                证据（{message.evidence.length}）
              </Button>
              {expanded && (
                <Box sx={{ mt: 1 }}>
                  {message.evidence.map((evidence, index) => (
                    <Chip
                      key={index}
                      label={`${evidence.type.toUpperCase()}：${evidence.table || evidence.id}（${evidence.score?.toFixed(2) || evidence.rows} 行）`}
                      size="small"
                      sx={{
                        mr: 1,
                        mb: 1,
                        backgroundColor: evidence.type === 'sql' ? '#2196F3' : '#9C27B0',
                        color: '#ffffff',
                      }}
                    />
                  ))}
                </Box>
              )}
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
};

export default MessageBubble;
