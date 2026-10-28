"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-26
"""
import sqlalchemy as sa
from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('buyers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('city', sa.String(length=80), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_buyers')),
    sa.UniqueConstraint('phone', name=op.f('uq_buyers_phone'))
    )
    op.create_table('campaigns',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('make', sa.String(length=60), nullable=False),
    sa.Column('model', sa.String(length=80), nullable=False),
    sa.Column('variant', sa.String(length=80), nullable=False),
    sa.Column('city', sa.String(length=80), nullable=False),
    sa.Column('ex_showroom_rupees', sa.Integer(), nullable=False),
    sa.Column('target_buyers', sa.Integer(), nullable=False),
    sa.Column('closes_on', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('winning_offer_id', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_campaigns'))
    )
    op.create_index(op.f('ix_campaigns_city'), 'campaigns', ['city'], unique=False)
    op.create_table('dealers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('city', sa.String(length=80), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.String(length=200), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dealers')),
    sa.UniqueConstraint('email', name=op.f('uq_dealers_email'))
    )
    op.create_index(op.f('ix_dealers_city'), 'dealers', ['city'], unique=False)
    op.create_table('otp_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('consumed', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_otp_codes'))
    )
    op.create_index(op.f('ix_otp_codes_phone'), 'otp_codes', ['phone'], unique=False)
    op.create_table('memberships',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('campaign_id', sa.Integer(), nullable=False),
    sa.Column('buyer_id', sa.Integer(), nullable=False),
    sa.Column('deposit_rupees', sa.Integer(), nullable=False),
    sa.Column('deposit_status', sa.String(length=20), nullable=False),
    sa.Column('deposit_ref', sa.String(length=100), nullable=True),
    sa.Column('share_contact', sa.Boolean(), nullable=False),
    sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['buyer_id'], ['buyers.id'], name=op.f('fk_memberships_buyer_id')),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], name=op.f('fk_memberships_campaign_id')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_memberships')),
    sa.UniqueConstraint('campaign_id', 'buyer_id', name=op.f('uq_memberships_campaign_id'))
    )
    op.create_index(op.f('ix_memberships_buyer_id'), 'memberships', ['buyer_id'], unique=False)
    op.create_index(op.f('ix_memberships_campaign_id'), 'memberships', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_memberships_deposit_ref'), 'memberships', ['deposit_ref'], unique=False)
    op.create_table('offers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('campaign_id', sa.Integer(), nullable=False),
    sa.Column('dealer_id', sa.Integer(), nullable=False),
    sa.Column('discount_rupees', sa.Integer(), nullable=False),
    sa.Column('freebies_value_rupees', sa.Integer(), nullable=False),
    sa.Column('valid_until', sa.Date(), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], name=op.f('fk_offers_campaign_id')),
    sa.ForeignKeyConstraint(['dealer_id'], ['dealers.id'], name=op.f('fk_offers_dealer_id')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_offers'))
    )
    op.create_index(op.f('ix_offers_campaign_id'), 'offers', ['campaign_id'], unique=False)
    # campaigns and offers reference each other, so this foreign key is added once both tables exist
    with op.batch_alter_table('campaigns') as batch:
        batch.create_foreign_key('fk_campaigns_winning_offer_id', 'offers', ['winning_offer_id'], ['id'])
    op.create_table('success_fees',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('campaign_id', sa.Integer(), nullable=False),
    sa.Column('dealer_id', sa.Integer(), nullable=False),
    sa.Column('deliveries', sa.Integer(), nullable=False),
    sa.Column('fee_per_delivery_rupees', sa.Integer(), nullable=False),
    sa.Column('amount_rupees', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], name=op.f('fk_success_fees_campaign_id')),
    sa.ForeignKeyConstraint(['dealer_id'], ['dealers.id'], name=op.f('fk_success_fees_dealer_id')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_success_fees')),
    sa.UniqueConstraint('campaign_id', name=op.f('uq_success_fees_campaign_id'))
    )
    op.create_index(op.f('ix_success_fees_dealer_id'), 'success_fees', ['dealer_id'], unique=False)
    op.create_table('deliveries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('membership_id', sa.Integer(), nullable=False),
    sa.Column('campaign_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('delivered_on', sa.Date(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], name=op.f('fk_deliveries_campaign_id')),
    sa.ForeignKeyConstraint(['membership_id'], ['memberships.id'], name=op.f('fk_deliveries_membership_id')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deliveries')),
    sa.UniqueConstraint('membership_id', name=op.f('uq_deliveries_membership_id'))
    )
    op.create_index(op.f('ix_deliveries_campaign_id'), 'deliveries', ['campaign_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_deliveries_campaign_id'), table_name='deliveries')
    op.drop_table('deliveries')
    op.drop_index(op.f('ix_success_fees_dealer_id'), table_name='success_fees')
    op.drop_table('success_fees')
    with op.batch_alter_table('campaigns') as batch:
        batch.drop_constraint('fk_campaigns_winning_offer_id', type_='foreignkey')
    op.drop_index(op.f('ix_offers_campaign_id'), table_name='offers')
    op.drop_table('offers')
    op.drop_index(op.f('ix_memberships_deposit_ref'), table_name='memberships')
    op.drop_index(op.f('ix_memberships_campaign_id'), table_name='memberships')
    op.drop_index(op.f('ix_memberships_buyer_id'), table_name='memberships')
    op.drop_table('memberships')
    op.drop_index(op.f('ix_otp_codes_phone'), table_name='otp_codes')
    op.drop_table('otp_codes')
    op.drop_index(op.f('ix_dealers_city'), table_name='dealers')
    op.drop_table('dealers')
    op.drop_index(op.f('ix_campaigns_city'), table_name='campaigns')
    op.drop_table('campaigns')
    op.drop_table('buyers')
