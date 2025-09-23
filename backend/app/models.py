from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class Sample(Base):
    __tablename__ = "samples"
    id = Column(Integer, primary_key=True, index=True)
    sample_id = Column(String, index=True, nullable=True)
    collection_date = Column(String, nullable=True)
    lab_name = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    metadata_json = Column(String, nullable=True)
    file_path = Column(String, nullable=False)

    metals = relationship("MetalConcentration", back_populates="sample", cascade="all,delete-orphan")
    assessments = relationship("MetalAssessment", back_populates="sample", cascade="all,delete-orphan")
    indices = relationship("SampleIndex", back_populates="sample", cascade="all,delete-orphan")

class MetalConcentration(Base):
    __tablename__ = "metal_concentrations"
    id = Column(Integer, primary_key=True, index=True)
    sample_id = Column(Integer, ForeignKey("samples.id"), index=True, nullable=False)
    metal = Column(String, index=True, nullable=False)
    value_mg_l = Column(Float, nullable=True)

    sample = relationship("Sample", back_populates="metals")


class MetalAssessment(Base):
    __tablename__ = "metal_assessments"
    id = Column(Integer, primary_key=True, index=True)
    sample_id = Column(Integer, ForeignKey("samples.id"), index=True, nullable=False)
    metal = Column(String, index=True, nullable=False)
    value_mg_l = Column(Float, nullable=True)
    limit_mg_l = Column(Float, nullable=True)
    exceeds_limit = Column(Integer, nullable=False, default=0)  # 0 = No, 1 = Yes
    # Audit fields
    raw_value = Column(String, nullable=True)
    raw_unit = Column(String, nullable=True)
    is_censored = Column(Integer, nullable=False, default=0)
    lod_reported = Column(Float, nullable=True)
    weight = Column(Float, nullable=True)
    validation_remark = Column(String, nullable=True)

    sample = relationship("Sample", back_populates="assessments")


class SampleIndex(Base):
    __tablename__ = "sample_indices"
    id = Column(Integer, primary_key=True, index=True)
    sample_id = Column(Integer, ForeignKey("samples.id"), index=True, nullable=False)
    hpi = Column(Float, nullable=True)
    hei = Column(Float, nullable=True)
    pli = Column(Float, nullable=True)
    cd_value = Column(Float, nullable=True)
    num_metals = Column(Integer, nullable=True)
    standard_id = Column(String, nullable=True)  # e.g., BIS_IS_10500_2012 or your version tag
    nd_policy_used = Column(String, nullable=True)

    sample = relationship("Sample", back_populates="indices")
